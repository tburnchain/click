"""위탁 확장 오케스트레이션 — 엔진(순수함수)과 DB 를 연결한다.

운영 플로우
  1) record_touchpoint  : 방문자 클릭을 이벤트 원장에 적재(집계 아님)
  2) record_conversion  : 네트워크 전환 콜백을 멱등 적재
  3) run_attribution    : 전환의 방문자 경로를 되짚어 터치포인트에 기여 배분
  4) refresh_metrics    : 파트너 일별 집계 + 베이지안 보정 지표 갱신
  5) rescore_partners   : 종합 스코어·티어 재산정(히스테리시스)
  6) run_fraud_scan     : 부정 신호 탐지·적재
  7) build_settlement   : 기간 정산 생성(다단계 배분·보류·최소지급)
각 단계는 멱등이며, 어트리뷰션 모델을 바꾸면 3)부터 소급 재계산할 수 있다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from psycopg import Connection

from gamdap.growth import fraud as fr
from gamdap.growth import scoring as sc
from gamdap.growth.attribution import Touch, attribute, credit_amounts
from gamdap.growth.settlement import (
    QUANT,
    Contract,
    PartnerNode,
    apply_holdback,
    resolve_contract,
    split_commission,
)
from gamdap.logging import get_logger

log = get_logger("growth.service")

_ZERO = Decimal("0")
DEFAULT_MODEL = "time_decay"
LOOKBACK_DAYS = 30


def _hash(value: str | None, salt: str = "tburn") -> str | None:
    """개인정보(IP/UA)는 원문 대신 솔트 해시만 저장."""
    if not value:
        return None
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:32]


# ─────────────────────────────────────────────────────────────
# 1. 파트너 등록 — 물질화 경로 유지
# ─────────────────────────────────────────────────────────────
def register_partner(conn: Connection, *, tenant_id: int, display_name: str,
                     parent_id: int | None = None, kind: str = "partner") -> dict:
    """파트너 생성. path/depth 를 부모로부터 유도해 하위트리 조회를 O(index) 로."""
    parent_path, parent_depth = "/", -1
    if parent_id:
        row = conn.execute("SELECT path, depth FROM core.partners WHERE id=%s",
                           (parent_id,)).fetchone()
        if not row:
            raise ValueError(f"상위 파트너 없음: {parent_id}")
        parent_path, parent_depth = row["path"], row["depth"]

    new = conn.execute(
        "INSERT INTO core.partners (tenant_id, parent_id, path, depth, kind, display_name) "
        "VALUES (%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (tenant_id) DO UPDATE SET display_name=EXCLUDED.display_name "
        "RETURNING id, path",
        (tenant_id, parent_id, "/", parent_depth + 1, kind, display_name)).fetchone()

    path = f"{parent_path}{new['id']}/" if parent_id else f"/{new['id']}/"
    conn.execute("UPDATE core.partners SET path=%s WHERE id=%s", (path, new["id"]))
    return {"id": new["id"], "path": path, "depth": parent_depth + 1}


def house_partner_id(conn: Connection) -> int:
    row = conn.execute("SELECT id FROM core.partners WHERE kind='house' ORDER BY id LIMIT 1").fetchone()
    if not row:
        raise RuntimeError("하우스 파트너 미존재 — 마이그레이션 0023 확인")
    return row["id"]


# ─────────────────────────────────────────────────────────────
# 2. 이벤트 적재
# ─────────────────────────────────────────────────────────────
def record_touchpoint(conn: Connection, *, visitor_id: str, partner_id: int | None,
                      site_id: int | None = None, offer_id: int | None = None,
                      network_id: int | None = None, channel: str = "direct",
                      device: str | None = None, country: str | None = None,
                      ip: str | None = None, user_agent: str | None = None,
                      session_id: str | None = None, is_bot: bool = False) -> int:
    """클릭 1건을 불변 이벤트로 적재. IP/UA 는 해시만 저장한다."""
    row = conn.execute(
        "INSERT INTO core.touchpoints (visitor_id, session_id, partner_id, site_id, offer_id, "
        "network_id, channel, device, country, ip_hash, ua_hash, is_bot) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (visitor_id, session_id, partner_id, site_id, offer_id, network_id, channel,
         device, (country or "")[:2] or None, _hash(ip), _hash(user_agent), is_bot)).fetchone()
    return row["id"]


def record_conversion(conn: Connection, *, visitor_id: str, network_id: int | None,
                      offer_id: int | None = None, order_ref: str | None = None,
                      gross_amount: Decimal | None = None, currency: str = "KRW",
                      commission_amount: Decimal | None = None,
                      commission_krw: Decimal | None = None,
                      status: str = "pending", raw: dict | None = None) -> int | None:
    """전환 적재(멱등). 같은 (network, order_ref) 는 중복 적재하지 않는다."""
    import json
    if order_ref and network_id:
        dup = conn.execute(
            "SELECT id FROM core.conversions WHERE network_id=%s AND order_ref=%s LIMIT 1",
            (network_id, order_ref)).fetchone()
        if dup:
            return dup["id"]
    row = conn.execute(
        "INSERT INTO core.conversions (visitor_id, network_id, offer_id, order_ref, "
        "gross_amount, currency, commission_amount, commission_krw, status, raw) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING id",
        (visitor_id, network_id, offer_id, order_ref, gross_amount, currency[:3],
         commission_amount, commission_krw, status,
         json.dumps(raw or {}, ensure_ascii=False))).fetchone()
    return row["id"]


# ─────────────────────────────────────────────────────────────
# 3. 어트리뷰션
# ─────────────────────────────────────────────────────────────
def run_attribution(conn: Connection, *, model: str = DEFAULT_MODEL,
                    lookback_days: int = LOOKBACK_DAYS, limit: int = 1000) -> dict:
    """미귀속 전환을 찾아 방문자 경로에 기여를 배분한다.

    같은 (전환, 모델) 조합은 UNIQUE 제약으로 중복 적재되지 않는다(멱등).
    """
    convs = conn.execute(
        "SELECT c.id, c.occurred_at, c.visitor_id, COALESCE(c.commission_krw,0) AS krw "
        "FROM core.conversions c "
        "WHERE NOT EXISTS (SELECT 1 FROM core.attributions a "
        "                  WHERE a.conversion_id=c.id AND a.model=%s) "
        "ORDER BY c.occurred_at DESC LIMIT %s", (model, limit)).fetchall()

    attributed = 0
    credited_total = _ZERO
    for cv in convs:
        tps = conn.execute(
            "SELECT id, partner_id, occurred_at, COALESCE(channel,'direct') AS channel "
            "FROM core.touchpoints "
            "WHERE visitor_id=%s AND occurred_at <= %s AND occurred_at >= %s "
            "  AND is_bot = FALSE "
            "ORDER BY occurred_at",
            (cv["visitor_id"], cv["occurred_at"],
             cv["occurred_at"] - timedelta(days=lookback_days))).fetchall()
        if not tps:
            continue

        touches = [Touch(touchpoint_id=t["id"], partner_id=t["partner_id"],
                         occurred_at=t["occurred_at"], channel=t["channel"]) for t in tps]
        weights = attribute(touches, model=model, lookback_days=lookback_days,
                            conversion_at=cv["occurred_at"])
        amounts = credit_amounts(weights, Decimal(str(cv["krw"] or 0)))

        for t, w, amt in zip(touches, weights, amounts, strict=True):
            if w <= 0:
                continue
            conn.execute(
                "INSERT INTO core.attributions (conversion_id, conversion_at, touchpoint_id, "
                "partner_id, model, weight, credited_krw) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (conversion_id, touchpoint_id, model) DO UPDATE "
                "SET weight=EXCLUDED.weight, credited_krw=EXCLUDED.credited_krw, "
                "    computed_at=now()",
                (cv["id"], cv["occurred_at"], t.touchpoint_id, t.partner_id, model,
                 round(w, 12), amt))
            credited_total += amt
        attributed += 1

    log.info("growth.attribution_done", model=model, conversions=attributed,
             credited_krw=str(credited_total))
    return {"model": model, "conversions": attributed, "credited_krw": credited_total}


# ─────────────────────────────────────────────────────────────
# 4. 파트너 집계·스코어링
# ─────────────────────────────────────────────────────────────
def refresh_metrics(conn: Connection, *, day: date | None = None,
                    model: str = DEFAULT_MODEL) -> int:
    """파트너 일별 실적 집계 + 베이지안 보정 지표 갱신(멱등 upsert)."""
    target = day or (datetime.now(UTC).date() - timedelta(days=1))
    rows = conn.execute(
        "WITH tp AS ("
        "  SELECT partner_id, count(*) clicks, count(DISTINCT visitor_id) uv "
        "  FROM core.touchpoints "
        "  WHERE occurred_at::date = %(d)s AND is_bot = FALSE AND partner_id IS NOT NULL "
        "  GROUP BY 1), "
        "at AS ("
        "  SELECT partner_id, count(DISTINCT conversion_id) convs, "
        "         COALESCE(sum(credited_krw),0) rev "
        "  FROM core.attributions "
        "  WHERE conversion_at::date = %(d)s AND model=%(m)s AND partner_id IS NOT NULL "
        "  GROUP BY 1) "
        "SELECT COALESCE(tp.partner_id, at.partner_id) partner_id, "
        "       COALESCE(tp.clicks,0) clicks, COALESCE(tp.uv,0) uv, "
        "       COALESCE(at.convs,0) convs, COALESCE(at.rev,0) rev "
        "FROM tp FULL OUTER JOIN at ON at.partner_id = tp.partner_id",
        {"d": target, "m": model}).fetchall()

    # 모집단 사전분포(수축용)
    stats = [sc.PartnerStats(partner_id=r["partner_id"], clicks=r["clicks"],
                             conversions=r["convs"], revenue_krw=float(r["rev"]),
                             unique_visitors=r["uv"]) for r in rows]
    priors = sc.cohort_priors(stats) if stats else None

    for r in rows:
        clicks, convs = r["clicks"], r["convs"]
        rev = float(r["rev"] or 0)
        if priors:
            alpha, beta = priors["prior_ab"]
            cvr = sc.shrink_rate(convs, clicks, alpha, beta)
            epc = sc.shrink_mean(rev, clicks, priors["prior_epc"])
        else:
            cvr = (convs / clicks) if clicks else 0.0
            epc = (rev / clicks) if clicks else 0.0
        conn.execute(
            "INSERT INTO core.partner_metrics_daily (partner_id, day, clicks, unique_visitors, "
            "conversions, revenue_krw, epc_krw, cvr, cvr_lower, computed_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) "
            "ON CONFLICT (partner_id, day) DO UPDATE SET clicks=EXCLUDED.clicks, "
            "  unique_visitors=EXCLUDED.unique_visitors, conversions=EXCLUDED.conversions, "
            "  revenue_krw=EXCLUDED.revenue_krw, epc_krw=EXCLUDED.epc_krw, cvr=EXCLUDED.cvr, "
            "  cvr_lower=EXCLUDED.cvr_lower, computed_at=now()",
            (r["partner_id"], target, clicks, r["uv"], convs, rev,
             round(epc, 6), round(cvr, 8), round(sc.wilson_lower_bound(convs, clicks), 8)))
    return len(rows)


def rescore_partners(conn: Connection, *, window_days: int = 30) -> int:
    """최근 window 실적으로 종합점수·티어 재산정(히스테리시스 적용)."""
    since = datetime.now(UTC).date() - timedelta(days=window_days)
    rows = conn.execute(
        "SELECT p.id, p.tier, p.tier_locked_until, "
        "       COALESCE(sum(m.clicks),0) clicks, COALESCE(sum(m.conversions),0) convs, "
        "       COALESCE(sum(m.revenue_krw),0) rev, COALESCE(sum(m.unique_visitors),0) uv, "
        "       count(m.day) active_days, "
        "       COALESCE((ip.channels->0->>'followers')::bigint, 0) followers "
        "FROM core.partners p "
        "LEFT JOIN core.partner_metrics_daily m ON m.partner_id=p.id AND m.day >= %s "
        "LEFT JOIN core.influencer_profiles ip ON ip.partner_id=p.id "
        "WHERE p.status='active' AND p.kind <> 'house' "
        "GROUP BY p.id, p.tier, p.tier_locked_until, ip.channels", (since,)).fetchall()
    if not rows:
        return 0

    stats = [sc.PartnerStats(
        partner_id=r["id"], clicks=r["clicks"], conversions=r["convs"],
        revenue_krw=float(r["rev"]), unique_visitors=r["uv"],
        followers=int(r["followers"] or 0), active_days=r["active_days"]) for r in rows]
    priors = sc.cohort_priors(stats)
    by_id = {r["id"]: r for r in rows}

    today = datetime.now(UTC).date()
    for s in stats:
        row = by_id[s.partner_id]
        result = sc.score_partner(s, current_tier=row["tier"], **priors)
        new_tier = result.tier
        # 티어 잠금 기간에는 강등하지 않는다(계약 안정성)
        locked = row["tier_locked_until"] and row["tier_locked_until"] >= today
        if locked and sc._TIER_ORDER.get(new_tier, 0) < sc._TIER_ORDER.get(row["tier"], 0):
            new_tier = row["tier"]
        conn.execute(
            "UPDATE core.partners SET tier=%s, tier_updated_at=now() WHERE id=%s",
            (new_tier, s.partner_id))
        conn.execute(
            "INSERT INTO core.influencer_profiles (partner_id, reach_score, engagement_score, "
            "conversion_score, fraud_score, composite_score, scored_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,now()) "
            "ON CONFLICT (partner_id) DO UPDATE SET reach_score=EXCLUDED.reach_score, "
            "  engagement_score=EXCLUDED.engagement_score, conversion_score=EXCLUDED.conversion_score, "
            "  fraud_score=EXCLUDED.fraud_score, composite_score=EXCLUDED.composite_score, "
            "  scored_at=now()",
            (s.partner_id, result.reach, result.engagement, result.conversion,
             result.fraud, result.composite))
    return len(stats)


# ─────────────────────────────────────────────────────────────
# 5. 부정 탐지
# ─────────────────────────────────────────────────────────────
def run_fraud_scan(conn: Connection, *, window_days: int = 7) -> int:
    """최근 트래픽에 대해 이상 신호를 탐지·적재."""
    import json
    since = datetime.now(UTC) - timedelta(days=window_days)
    partners = conn.execute(
        "SELECT DISTINCT partner_id FROM core.touchpoints "
        "WHERE occurred_at >= %s AND partner_id IS NOT NULL", (since,)).fetchall()
    if not partners:
        return 0

    # 모집단 CVR(이상치 판정 기준)
    pop = conn.execute(
        "SELECT CASE WHEN sum(clicks)>0 THEN sum(conversions)::float/sum(clicks) ELSE 0 END cvr "
        "FROM core.partner_metrics_daily WHERE day >= %s GROUP BY partner_id "
        "HAVING sum(clicks) > 0", (since.date(),)).fetchall()
    population_cvr = [float(r["cvr"]) for r in pop]

    found = 0
    for p in partners:
        pid = p["partner_id"]
        tps = conn.execute(
            "SELECT occurred_at, ip_hash, is_bot FROM core.touchpoints "
            "WHERE partner_id=%s AND occurred_at >= %s", (pid, since)).fetchall()
        if not tps:
            continue
        hours = [t["occurred_at"].hour for t in tps]
        ips = [t["ip_hash"] for t in tps if t["ip_hash"]]
        bots = sum(1 for t in tps if t["is_bot"])
        clicks = len(tps)
        conv_row = conn.execute(
            "SELECT count(DISTINCT conversion_id) c FROM core.attributions "
            "WHERE partner_id=%s AND conversion_at >= %s", (pid, since)).fetchone()
        convs = conv_row["c"] if conv_row else 0
        cvr = (convs / clicks) if clicks else 0.0
        baseline = clicks / max(1.0, window_days * 24.0)
        recent = conn.execute(
            "SELECT count(*) c FROM core.touchpoints WHERE partner_id=%s "
            "AND occurred_at >= now() - interval '1 hour'", (pid,)).fetchone()["c"]

        signals = fr.evaluate_partner(
            hours=hours, ip_hashes=ips, recent_clicks=recent, baseline_hourly=baseline,
            cvr=cvr, population_cvr=population_cvr, clicks=clicks, bot_clicks=bots)
        for s in signals:
            conn.execute(
                "INSERT INTO core.fraud_signals (partner_id, kind, severity, score, evidence) "
                "VALUES (%s,%s,%s,%s,%s::jsonb)",
                (pid, s.kind, s.severity, round(s.score, 4),
                 json.dumps(s.evidence, ensure_ascii=False)))
            found += 1
        if signals:
            conn.execute(
                "UPDATE core.influencer_profiles SET fraud_score=%s WHERE partner_id=%s",
                (fr.risk_score(signals), pid))
    return found


# ─────────────────────────────────────────────────────────────
# 6. 정산
# ─────────────────────────────────────────────────────────────
def _partner_nodes(conn: Connection) -> dict[int, PartnerNode]:
    rows = conn.execute("SELECT id, parent_id, kind FROM core.partners").fetchall()
    return {r["id"]: PartnerNode(partner_id=r["id"], parent_id=r["parent_id"], kind=r["kind"])
            for r in rows}


def _contract_for(conn: Connection, partner_id: int, tier: str) -> Contract:
    """파트너의 적용 계약. 없으면 티어 기본값(계약 미체결도 정산 가능)."""
    rows = conn.execute(
        "SELECT id, scope, revenue_share, override_rates, holdback_rate, holdback_days, "
        "       min_payout_krw, priority FROM core.consignment_contracts "
        "WHERE partner_id=%s AND status='active' "
        "  AND effective_from <= CURRENT_DATE "
        "  AND (effective_to IS NULL OR effective_to >= CURRENT_DATE) "
        "ORDER BY priority", (partner_id,)).fetchall()
    picked = resolve_contract([dict(r) for r in rows]) if rows else None
    if picked:
        return Contract(
            partner_id=partner_id,
            revenue_share=Decimal(str(picked["revenue_share"])),
            override_rates=tuple(Decimal(str(x)) for x in (picked["override_rates"] or [])),
            holdback_rate=Decimal(str(picked["holdback_rate"])),
            holdback_days=picked["holdback_days"],
            min_payout_krw=Decimal(str(picked["min_payout_krw"])),
        )
    # 티어별 기본 배분율 — 상위 티어일수록 파트너 몫이 크다(성과 인센티브)
    default_share = {"bronze": "0.50", "silver": "0.60", "gold": "0.70",
                     "platinum": "0.78", "diamond": "0.85"}.get(tier, "0.50")
    return Contract(partner_id=partner_id, revenue_share=Decimal(default_share),
                    override_rates=(Decimal("0.05"), Decimal("0.02")),
                    holdback_rate=Decimal("0.10"), holdback_days=30,
                    min_payout_krw=Decimal("10000"))


def build_settlement(conn: Connection, *, period_start: date, period_end: date,
                     model: str = DEFAULT_MODEL) -> dict:
    """기간 정산 생성. 파트너별 귀속액을 계약대로 배분해 지급액을 확정한다.

    불변식: 배분 합계 = 귀속 수수료 총액(하우스가 잔차 흡수).
    """
    nodes = _partner_nodes(conn)
    house = house_partner_id(conn)

    rows = conn.execute(
        "SELECT a.partner_id, p.tier, sum(a.credited_krw) gross "
        "FROM core.attributions a JOIN core.partners p ON p.id=a.partner_id "
        "WHERE a.model=%s AND a.conversion_at::date BETWEEN %s AND %s "
        "  AND a.partner_id IS NOT NULL AND p.status='active' "
        "GROUP BY 1,2 HAVING sum(a.credited_krw) > 0", (model, period_start, period_end)).fetchall()

    # 파트너별 누계(자기 몫 + 하위로부터의 오버라이드)
    share_of: dict[int, Decimal] = {}
    override_of: dict[int, Decimal] = {}
    gross_of: dict[int, Decimal] = {}
    lines: list[tuple] = []
    total_gross = _ZERO

    for r in rows:
        pid = r["partner_id"]
        gross = Decimal(str(r["gross"])).quantize(QUANT)
        gross_of[pid] = gross
        total_gross += gross
        contract = _contract_for(conn, pid, r["tier"])
        result = split_commission(gross, contract=contract, nodes=nodes, house_partner_id=house)
        for ln in result.lines:
            if ln.kind == "attribution":
                share_of[ln.partner_id] = share_of.get(ln.partner_id, _ZERO) + ln.amount
            elif ln.kind == "override":
                override_of[ln.partner_id] = override_of.get(ln.partner_id, _ZERO) + ln.amount
            else:
                share_of[house] = share_of.get(house, _ZERO) + ln.amount
            lines.append((ln.partner_id, ln.kind, ln.amount, ln.source_partner_id))

    created = 0
    payable_total = _ZERO
    for pid in set(share_of) | set(override_of):
        tier_row = conn.execute("SELECT tier FROM core.partners WHERE id=%s", (pid,)).fetchone()
        contract = _contract_for(conn, pid, tier_row["tier"] if tier_row else "bronze")
        share = share_of.get(pid, _ZERO)
        override = override_of.get(pid, _ZERO)
        subtotal = share + override
        payable, hold = apply_holdback(subtotal, contract)
        # 최소지급액 미만은 전액 이월(다음 기수로) — 소액 송금비용 방지
        carried = _ZERO
        if payable < contract.min_payout_krw and pid != house:
            carried, payable = payable, _ZERO

        st = conn.execute(
            "INSERT INTO core.settlements (partner_id, period_start, period_end, gross_krw, "
            "share_krw, override_krw, holdback_krw, payable_krw, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'draft') "
            "ON CONFLICT (partner_id, period_start, period_end) DO UPDATE SET "
            "  gross_krw=EXCLUDED.gross_krw, share_krw=EXCLUDED.share_krw, "
            "  override_krw=EXCLUDED.override_krw, holdback_krw=EXCLUDED.holdback_krw, "
            "  payable_krw=EXCLUDED.payable_krw, computed_at=now() RETURNING id",
            (pid, period_start, period_end, gross_of.get(pid, _ZERO), share, override,
             hold + carried, payable)).fetchone()
        conn.execute("DELETE FROM core.settlement_lines WHERE settlement_id=%s", (st["id"],))
        for lp, kind, amt, src in lines:
            if lp != pid:
                continue
            conn.execute(
                "INSERT INTO core.settlement_lines (settlement_id, kind, amount_krw, "
                "source_partner_id) VALUES (%s,%s,%s,%s)",
                (st["id"], "attribution" if kind in ("attribution", "house") else "override",
                 amt, src))
        if hold > 0:
            conn.execute(
                "INSERT INTO core.settlement_lines (settlement_id, kind, amount_krw, memo) "
                "VALUES (%s,'holdback',%s,%s)",
                (st["id"], -hold, f"{contract.holdback_days}일 보류(반품 대비)"))
        if carried > 0:
            conn.execute(
                "INSERT INTO core.settlement_lines (settlement_id, kind, amount_krw, memo) "
                "VALUES (%s,'adjust',%s,%s)",
                (st["id"], -carried, f"최소지급액 {contract.min_payout_krw} 미만 → 이월"))
        created += 1
        payable_total += payable

    log.info("growth.settlement_built", period=f"{period_start}~{period_end}",
             partners=created, gross=str(total_gross), payable=str(payable_total))
    return {"partners": created, "gross_krw": total_gross, "payable_krw": payable_total,
            "period": f"{period_start}~{period_end}"}


def pipeline(conn_factory, *, day: date | None = None, model: str = DEFAULT_MODEL) -> dict:
    """일일 운영 파이프라인 — 귀속 → 집계 → 스코어 → 부정탐지 순으로 실행."""
    out: dict = {}
    with conn_factory() as conn:
        out["attribution"] = run_attribution(conn, model=model)
    with conn_factory() as conn:
        out["metrics"] = refresh_metrics(conn, day=day, model=model)
    with conn_factory() as conn:
        out["scored"] = rescore_partners(conn)
    with conn_factory() as conn:
        out["fraud_signals"] = run_fraud_scan(conn)
    return out


def partner_tree(conn: Connection, root_id: int | None = None) -> Sequence[dict]:
    """파트너 트리 조회(물질화 경로 기반, 단일 쿼리)."""
    if root_id:
        row = conn.execute("SELECT path FROM core.partners WHERE id=%s", (root_id,)).fetchone()
        if not row:
            return []
        return conn.execute(
            "SELECT p.id, p.parent_id, p.depth, p.kind, p.display_name, p.tier, p.status, "
            "       ip.composite_score, ip.fraud_score "
            "FROM core.partners p LEFT JOIN core.influencer_profiles ip ON ip.partner_id=p.id "
            "WHERE p.path LIKE %s ORDER BY p.path", (row["path"] + "%",)).fetchall()
    return conn.execute(
        "SELECT p.id, p.parent_id, p.depth, p.kind, p.display_name, p.tier, p.status, "
        "       ip.composite_score, ip.fraud_score "
        "FROM core.partners p LEFT JOIN core.influencer_profiles ip ON ip.partner_id=p.id "
        "ORDER BY p.path").fetchall()

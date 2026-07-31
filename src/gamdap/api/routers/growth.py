"""위탁 확장 운영 API — 파트너/인플루언서 관리, 추적, 정산.

경로: /api/v1/growth/*
추적 엔드포인트(/track/*)는 공개(방문자 브라우저가 호출), 관리 엔드포인트는
운영자용이다. 실제 배포 시 관리 경로는 API 키 게이트 뒤에 둔다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from gamdap.api.auth import require_partner, require_scope
from gamdap.db import transaction
from gamdap.growth import ingest_conversions as ic
from gamdap.growth import service as gs

router = APIRouter(prefix="/api/v1/growth", tags=["growth"])

# 스코프 게이트 — 읽기 키로 정산을 실행할 수 없다.
READ = Depends(require_scope("growth:read"))
WRITE = Depends(require_scope("growth:write"))
SETTLE = Depends(require_scope("growth:settle"))
ADMIN = Depends(require_scope("admin"))


# ── 스키마 ────────────────────────────────────────────────────
class PartnerIn(BaseModel):
    tenant_id: int
    display_name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None
    kind: str = Field("partner", pattern="^(agency|partner|influencer)$")


class TrackClickIn(BaseModel):
    visitor_id: str = Field(min_length=8, max_length=128)
    partner_id: int | None = None
    site_id: int | None = None
    offer_id: int | None = None
    network_id: int | None = None
    channel: str = Field("direct", max_length=32)
    device: str | None = None
    country: str | None = None
    session_id: str | None = None


class ConversionIn(BaseModel):
    visitor_id: str
    network_id: int | None = None
    offer_id: int | None = None
    order_ref: str | None = None
    gross_amount: Decimal | None = None
    currency: str = "KRW"
    commission_amount: Decimal | None = None
    commission_krw: Decimal | None = None
    status: str = Field("pending", pattern="^(pending|approved|rejected|paid)$")


class ContractIn(BaseModel):
    partner_id: int
    revenue_share: Decimal = Field(ge=0, le=1)
    override_rates: list[Decimal] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)
    holdback_rate: Decimal = Field(Decimal("0"), ge=0, lt=1)
    holdback_days: int = 30
    min_payout_krw: Decimal = Decimal("10000")


# ── 파트너 관리 ───────────────────────────────────────────────
@router.post("/partners")
def create_partner(body: PartnerIn, _=WRITE) -> dict:
    with transaction() as conn:
        parent = body.parent_id or gs.house_partner_id(conn)
        try:
            return gs.register_partner(conn, tenant_id=body.tenant_id,
                                       display_name=body.display_name,
                                       parent_id=parent, kind=body.kind)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.get("/partners")
def list_partners(root_id: int | None = None, _=READ) -> list[dict]:
    with transaction() as conn:
        return [dict(r) for r in gs.partner_tree(conn, root_id)]


@router.get("/partners/{partner_id}")
def partner_detail(partner_id: int, days: int = Query(30, ge=1, le=365), _=READ) -> dict:
    since = datetime.now(UTC).date() - timedelta(days=days)
    with transaction() as conn:
        p = conn.execute(
            "SELECT p.*, ip.reach_score, ip.engagement_score, ip.conversion_score, "
            "       ip.fraud_score, ip.composite_score, ip.channels, ip.audience "
            "FROM core.partners p LEFT JOIN core.influencer_profiles ip ON ip.partner_id=p.id "
            "WHERE p.id=%s", (partner_id,)).fetchone()
        if not p:
            raise HTTPException(404, "파트너 없음")
        metrics = conn.execute(
            "SELECT day, clicks, unique_visitors, conversions, revenue_krw, epc_krw, "
            "       cvr, cvr_lower FROM core.partner_metrics_daily "
            "WHERE partner_id=%s AND day >= %s ORDER BY day", (partner_id, since)).fetchall()
        signals = conn.execute(
            "SELECT kind, severity, score, evidence, detected_at FROM core.fraud_signals "
            "WHERE partner_id=%s AND resolved_at IS NULL ORDER BY detected_at DESC LIMIT 20",
            (partner_id,)).fetchall()
        children = conn.execute(
            "SELECT count(*) n FROM core.partners WHERE parent_id=%s", (partner_id,)).fetchone()
        return {"partner": dict(p), "metrics": [dict(m) for m in metrics],
                "fraud_signals": [dict(s) for s in signals], "children": children["n"]}


# ── 추적(공개) ────────────────────────────────────────────────
@router.post("/track/click")
def track_click(body: TrackClickIn) -> dict:
    """클릭 이벤트 적재. 방문자 IP/UA 는 해시로만 저장한다."""
    with transaction() as conn:
        tid = gs.record_touchpoint(
            conn, visitor_id=body.visitor_id, partner_id=body.partner_id,
            site_id=body.site_id, offer_id=body.offer_id, network_id=body.network_id,
            channel=body.channel, device=body.device, country=body.country,
            session_id=body.session_id)
    return {"touchpoint_id": tid}


@router.post("/track/conversion")
def track_conversion(body: ConversionIn) -> dict:
    """네트워크 전환 콜백. (network_id, order_ref) 로 멱등 처리."""
    with transaction() as conn:
        cid = gs.record_conversion(
            conn, visitor_id=body.visitor_id, network_id=body.network_id,
            offer_id=body.offer_id, order_ref=body.order_ref,
            gross_amount=body.gross_amount, currency=body.currency,
            commission_amount=body.commission_amount,
            commission_krw=body.commission_krw, status=body.status)
    return {"conversion_id": cid}


# ── 위탁 계약 ─────────────────────────────────────────────────
@router.post("/contracts")
def create_contract(body: ContractIn, _=WRITE) -> dict:
    import json
    total = body.revenue_share + sum(body.override_rates)
    if total > 1:
        raise HTTPException(400, f"배분 비율 합이 1을 초과합니다({total}) — 지급 불능")
    with transaction() as conn:
        row = conn.execute(
            "INSERT INTO core.consignment_contracts (partner_id, scope, revenue_share, "
            "override_rates, holdback_rate, holdback_days, min_payout_krw, status) "
            "VALUES (%s,%s::jsonb,%s,%s,%s,%s,%s,'active') RETURNING id",
            (body.partner_id, json.dumps(body.scope, ensure_ascii=False), body.revenue_share,
             body.override_rates, body.holdback_rate, body.holdback_days,
             body.min_payout_krw)).fetchone()
    return {"contract_id": row["id"]}


# ── 운영 파이프라인 ───────────────────────────────────────────
@router.post("/pipeline/attribution")
def run_attribution(model: str = Query("time_decay"), limit: int = Query(1000, le=5000), _=WRITE) -> dict:
    from gamdap.growth.attribution import MODELS
    if model not in MODELS:
        raise HTTPException(400, f"지원 모델: {', '.join(MODELS)}")
    with transaction() as conn:
        rep = gs.run_attribution(conn, model=model, limit=limit)
    return {**rep, "credited_krw": str(rep["credited_krw"])}


@router.post("/pipeline/daily")
def run_daily(day: date | None = None, _=WRITE) -> dict:
    """일일 파이프라인 — 귀속 → 집계 → 스코어링 → 부정탐지."""
    return gs.pipeline(transaction, day=day)


@router.post("/settlements/build")
def build_settlement(period_start: date, period_end: date,
                     model: str = Query("time_decay"), _=SETTLE) -> dict:
    if period_end < period_start:
        raise HTTPException(400, "기간이 올바르지 않습니다")
    with transaction() as conn:
        r = gs.build_settlement(conn, period_start=period_start, period_end=period_end,
                                model=model)
    return {**r, "gross_krw": str(r["gross_krw"]), "payable_krw": str(r["payable_krw"])}


@router.get("/settlements")
def list_settlements(partner_id: int | None = None, limit: int = Query(50, le=200), _=READ) -> list[dict]:
    with transaction() as conn:
        if partner_id:
            rows = conn.execute(
                "SELECT s.*, p.display_name, p.tier FROM core.settlements s "
                "JOIN core.partners p ON p.id=s.partner_id WHERE s.partner_id=%s "
                "ORDER BY s.period_end DESC LIMIT %s", (partner_id, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT s.*, p.display_name, p.tier FROM core.settlements s "
                "JOIN core.partners p ON p.id=s.partner_id "
                "ORDER BY s.period_end DESC, s.payable_krw DESC LIMIT %s", (limit,)).fetchall()
        return [dict(r) for r in rows]


@router.get("/leaderboard")
def leaderboard(days: int = Query(30, ge=1, le=365), limit: int = Query(50, le=200), _=READ) -> list[dict]:
    """파트너 성과 순위 — 종합점수 기준(소표본 왜곡 보정 완료)."""
    since = datetime.now(UTC).date() - timedelta(days=days)
    with transaction() as conn:
        rows = conn.execute(
            "SELECT p.id, p.display_name, p.kind, p.tier, "
            "       COALESCE(ip.composite_score,0) score, COALESCE(ip.fraud_score,0) fraud, "
            "       COALESCE(sum(m.clicks),0) clicks, COALESCE(sum(m.conversions),0) conversions, "
            "       COALESCE(sum(m.revenue_krw),0) revenue_krw, "
            "       CASE WHEN sum(m.clicks) > 0 "
            "            THEN sum(m.revenue_krw)/sum(m.clicks) ELSE 0 END epc_krw "
            "FROM core.partners p "
            "LEFT JOIN core.influencer_profiles ip ON ip.partner_id=p.id "
            "LEFT JOIN core.partner_metrics_daily m ON m.partner_id=p.id AND m.day >= %s "
            "WHERE p.status='active' AND p.kind <> 'house' "
            "GROUP BY p.id, p.display_name, p.kind, p.tier, ip.composite_score, ip.fraud_score "
            "ORDER BY score DESC, revenue_krw DESC LIMIT %s", (since, limit)).fetchall()
        return [dict(r) for r in rows]


@router.get("/overview")
def overview(days: int = Query(30, ge=1, le=365), _=READ) -> dict:
    """위탁 네트워크 전체 현황 — 관리 대시보드용 요약."""
    since = datetime.now(UTC).date() - timedelta(days=days)
    with transaction() as conn:
        agg = conn.execute(
            "SELECT count(DISTINCT p.id) partners, "
            "       count(DISTINCT p.id) FILTER (WHERE p.kind='influencer') influencers, "
            "       COALESCE(sum(m.clicks),0) clicks, COALESCE(sum(m.conversions),0) conversions, "
            "       COALESCE(sum(m.revenue_krw),0) revenue_krw "
            "FROM core.partners p "
            "LEFT JOIN core.partner_metrics_daily m ON m.partner_id=p.id AND m.day >= %s "
            "WHERE p.status='active' AND p.kind <> 'house'", (since,)).fetchone()
        tiers = conn.execute(
            "SELECT tier, count(*) n FROM core.partners "
            "WHERE status='active' AND kind <> 'house' GROUP BY 1", ()).fetchall()
        # interval 은 문자열 보간이 아닌 파라미터로 — SQL 인젝션 차단
        risk = conn.execute(
            "SELECT severity, count(*) n FROM core.fraud_signals "
            "WHERE resolved_at IS NULL AND detected_at >= now() - make_interval(days => %s) "
            "GROUP BY 1", (days,)).fetchall()
        pending = conn.execute(
            "SELECT COALESCE(sum(payable_krw),0) amount, count(*) n FROM core.settlements "
            "WHERE status IN ('draft','confirmed')", ()).fetchone()
        d = dict(agg)
        clicks = float(d.get("clicks") or 0)
        convs = float(d.get("conversions") or 0)
        return {
            **d,
            "cvr": (convs / clicks) if clicks else 0.0,
            "epc_krw": (float(d.get("revenue_krw") or 0) / clicks) if clicks else 0.0,
            "tiers": {r["tier"]: r["n"] for r in tiers},
            "open_risk": {r["severity"]: r["n"] for r in risk},
            "pending_payout_krw": str(pending["amount"]), "pending_settlements": pending["n"],
        }


# ─────────────────────────────────────────────────────────────
# 전환 데이터 원천 — push(포스트백) · file(임포트) · 원천 설정
# ─────────────────────────────────────────────────────────────
class SourceIn(BaseModel):
    network_code: str = Field(min_length=2, max_length=64)
    network_id: int | None = None
    mode: str = Field("push", pattern="^(push|pull|file)$")
    secret: str | None = None            # 저장 시 암호화, 응답에 절대 포함 안 됨
    param_map: dict = Field(default_factory=dict)
    click_param: str | None = None
    allow_ips: list[str] = Field(default_factory=list)
    report_url: str | None = None
    signature_algo: str = Field("hmac_sha256", pattern="^(hmac_sha256|none)$")
    default_status: str = Field("pending", pattern="^(pending|approved)$")


@router.post("/sources")
def upsert_source(body: SourceIn, _=ADMIN) -> dict:
    """전환 원천 등록. 공유 비밀은 암호화 저장되며 다시 조회할 수 없다."""
    with transaction() as conn:
        sid = ic.upsert_source(
            conn, network_code=body.network_code, network_id=body.network_id,
            mode=body.mode, secret=body.secret, param_map=body.param_map,
            click_param=body.click_param, allow_ips=body.allow_ips,
            report_url=body.report_url, signature_algo=body.signature_algo,
            default_status=body.default_status)
    return {"source_id": sid, "network_code": body.network_code, "mode": body.mode}


@router.get("/sources")
def list_sources(_=READ) -> list[dict]:
    """등록된 전환 원천. 비밀은 보유 여부만 노출한다."""
    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, network_code, network_id, mode, param_map, click_param, allow_ips, "
            "       report_url, signature_algo, default_status, is_active, last_pulled_at, "
            "       (secret_enc IS NOT NULL) AS has_secret "
            "FROM core.conversion_sources ORDER BY network_code").fetchall()
        return [dict(r) for r in rows]


@router.api_route("/postback/{network_code}", methods=["GET", "POST"])
async def receive_postback(network_code: str, request: Request) -> dict:
    """네트워크 S2S 포스트백 수신(공개 — 서명으로 인증).

    GET 쿼리스트링과 POST 폼/JSON 을 모두 받는다(네트워크마다 방식이 다름).
    거부되어도 200 으로 응답한다 — 네트워크 재시도 폭주를 막고, 사유는 로그로 남긴다.
    """
    raw: dict = dict(request.query_params)
    if request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict):
                raw.update({str(k): v for k, v in body.items()})
        except (ValueError, TypeError):
            # JSON 이 아니면 폼으로 시도. python-multipart 부재 시 starlette 은
            # AssertionError 를 던지므로 Exception 으로 받는다(수신은 절대 죽으면 안 됨).
            try:
                form = await request.form()
                raw.update({str(k): str(v) for k, v in form.items()})
            except Exception:  # noqa: BLE001 — 어떤 파싱 실패든 쿼리스트링으로 진행
                pass
    client_ip = request.client.host if request.client else None
    # 프록시(Cloudflare/nginx) 뒤에서는 원 발신 IP 가 헤더에 있다
    fwd = request.headers.get("cf-connecting-ip") or request.headers.get("x-real-ip")
    source_ip = fwd or client_ip

    with transaction() as conn:
        result = ic.handle_postback(conn, network_code=network_code, raw=raw,
                                    source_ip=source_ip)
    return {"ok": result.accepted, "outcome": result.outcome,
            "conversion_id": result.conversion_id, "detail": result.detail}


class ImportIn(BaseModel):
    network_code: str
    rows: list[dict] = Field(min_length=1, max_length=5000)


@router.post("/conversions/import")
def import_conversions(body: ImportIn, _=WRITE) -> dict:
    """리포트 행 일괄 임포트(대부분의 네트워크가 이 경로)."""
    with transaction() as conn:
        try:
            tally = ic.import_rows(conn, network_code=body.network_code, rows=body.rows)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    with transaction() as conn:
        tally["direct_attributed"] = ic.attribute_direct(conn)
    return tally


@router.get("/postback/logs")
def postback_logs(outcome: str | None = None, limit: int = Query(100, le=500),
                  _=READ) -> list[dict]:
    """포스트백 수신 이력. 거부 사유까지 남아 분쟁 시 증거가 된다."""
    with transaction() as conn:
        if outcome:
            rows = conn.execute(
                "SELECT * FROM core.postback_log WHERE outcome=%s "
                "ORDER BY received_at DESC LIMIT %s", (outcome, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM core.postback_log ORDER BY received_at DESC LIMIT %s",
                (limit,)).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────
# API 키 관리 — 발급/폐기 (admin 전용)
# ─────────────────────────────────────────────────────────────
class ApiKeyIn(BaseModel):
    tenant_id: int
    label: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(min_length=1)
    expires_days: int | None = Field(None, ge=1, le=3650)


@router.post("/apikeys")
def issue_api_key(body: ApiKeyIn, _=ADMIN) -> dict:
    """API 키 발급. 원문은 이 응답에서만 볼 수 있다(해시만 저장)."""
    from gamdap.api.auth import create_api_key
    with transaction() as conn:
        try:
            return create_api_key(conn, tenant_id=body.tenant_id, label=body.label,
                                  scopes=body.scopes, expires_days=body.expires_days)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.get("/apikeys")
def list_api_keys(_=ADMIN) -> list[dict]:
    """발급된 키 목록. 원문·해시는 노출하지 않는다."""
    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, tenant_id, label, prefix, scopes, is_active, created_at, "
            "       last_used_at, expires_at FROM core.api_keys ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


@router.delete("/apikeys/{key_id}")
def revoke_api_key(key_id: int, _=ADMIN) -> dict:
    with transaction() as conn:
        row = conn.execute(
            "UPDATE core.api_keys SET is_active=FALSE WHERE id=%s RETURNING id", (key_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "키를 찾을 수 없습니다")
    return {"revoked": key_id}


# ─────────────────────────────────────────────────────────────
# 파트너 대시보드 — 로그인한 파트너가 '자기 데이터만' 조회
# ─────────────────────────────────────────────────────────────
@router.post("/partner/login")
def partner_login(partner_id: int, _=ADMIN) -> dict:
    """파트너 세션 발급(운영자가 대행 발급). 파트너 자체 로그인은 회원 계정과 연동한다."""
    from gamdap.api.auth import issue_partner_session
    with transaction() as conn:
        exists = conn.execute("SELECT id FROM core.partners WHERE id=%s AND status='active'",
                              (partner_id,)).fetchone()
        if not exists:
            raise HTTPException(404, "활성 파트너가 아닙니다")
        return issue_partner_session(conn, partner_id=partner_id)


@router.get("/me")
def partner_me(ctx: dict = Depends(require_partner),
               days: int = Query(30, ge=1, le=365)) -> dict:
    """파트너 자신의 대시보드 데이터 — 실적·등급·정산·하위 파트너."""
    pid = ctx["partner_id"]
    since = datetime.now(UTC).date() - timedelta(days=days)
    with transaction() as conn:
        profile = conn.execute(
            "SELECT p.id, p.display_name, p.kind, p.tier, p.depth, p.created_at, "
            "       ip.reach_score, ip.engagement_score, ip.conversion_score, "
            "       ip.composite_score, ip.fraud_score "
            "FROM core.partners p LEFT JOIN core.influencer_profiles ip ON ip.partner_id=p.id "
            "WHERE p.id=%s", (pid,)).fetchone()
        series = conn.execute(
            "SELECT day, clicks, unique_visitors, conversions, revenue_krw, epc_krw, cvr "
            "FROM core.partner_metrics_daily WHERE partner_id=%s AND day >= %s ORDER BY day",
            (pid, since)).fetchall()
        totals = conn.execute(
            "SELECT COALESCE(sum(clicks),0) clicks, COALESCE(sum(conversions),0) conversions, "
            "       COALESCE(sum(revenue_krw),0) revenue_krw "
            "FROM core.partner_metrics_daily WHERE partner_id=%s AND day >= %s",
            (pid, since)).fetchone()
        settlements = conn.execute(
            "SELECT period_start, period_end, gross_krw, share_krw, override_krw, "
            "       holdback_krw, payable_krw, status FROM core.settlements "
            "WHERE partner_id=%s ORDER BY period_end DESC LIMIT 12", (pid,)).fetchall()
        # 하위 파트너(오버라이드 수익원) — 자기 트리만
        children = conn.execute(
            "SELECT p.id, p.display_name, p.kind, p.tier, "
            "       COALESCE(sum(m.clicks),0) clicks, COALESCE(sum(m.revenue_krw),0) revenue_krw "
            "FROM core.partners p "
            "LEFT JOIN core.partner_metrics_daily m ON m.partner_id=p.id AND m.day >= %s "
            "WHERE p.parent_id=%s AND p.status='active' "
            "GROUP BY p.id, p.display_name, p.kind, p.tier "
            "ORDER BY revenue_krw DESC LIMIT 50", (since, pid)).fetchall()
        unpaid = conn.execute(
            "SELECT COALESCE(sum(payable_krw),0) amt FROM core.settlements "
            "WHERE partner_id=%s AND status IN ('draft','confirmed')", (pid,)).fetchone()

    t = dict(totals)
    clicks = float(t["clicks"] or 0)
    return {
        "profile": dict(profile) if profile else None,
        "totals": {**t, "cvr": (float(t["conversions"]) / clicks) if clicks else 0.0,
                   "epc_krw": (float(t["revenue_krw"]) / clicks) if clicks else 0.0},
        "series": [dict(r) for r in series],
        "settlements": [dict(r) for r in settlements],
        "children": [dict(r) for r in children],
        "unpaid_krw": str(unpaid["amt"]),
    }


# ─────────────────────────────────────────────────────────────
# 어트리뷰션 모델 상태 — 표본 충분 시 고급 모델 활성화
# ─────────────────────────────────────────────────────────────
@router.get("/models")
def model_states(_=READ) -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            "SELECT model, is_enabled, paths_observed, conversions_obs, channels_obs, "
            "       min_paths, min_conversions, stability, evaluated_at, note "
            "FROM core.attribution_model_state ORDER BY model").fetchall()
        return [dict(r) for r in rows]


@router.post("/models/evaluate")
def evaluate_models(_=WRITE) -> dict:
    """표본이 통계적 검정력을 만족하는지 평가하고, 충족 시 고급 모델을 켠다."""
    from gamdap.growth.model_gate import evaluate_all
    with transaction() as conn:
        return evaluate_all(conn)

"""위탁 확장 운영 API — 파트너/인플루언서 관리, 추적, 정산.

경로: /api/v1/growth/*
추적 엔드포인트(/track/*)는 공개(방문자 브라우저가 호출), 관리 엔드포인트는
운영자용이다. 실제 배포 시 관리 경로는 API 키 게이트 뒤에 둔다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from gamdap.db import transaction
from gamdap.growth import service as gs

router = APIRouter(prefix="/api/v1/growth", tags=["growth"])


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
def create_partner(body: PartnerIn) -> dict:
    with transaction() as conn:
        parent = body.parent_id or gs.house_partner_id(conn)
        try:
            return gs.register_partner(conn, tenant_id=body.tenant_id,
                                       display_name=body.display_name,
                                       parent_id=parent, kind=body.kind)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.get("/partners")
def list_partners(root_id: int | None = None) -> list[dict]:
    with transaction() as conn:
        return [dict(r) for r in gs.partner_tree(conn, root_id)]


@router.get("/partners/{partner_id}")
def partner_detail(partner_id: int, days: int = Query(30, ge=1, le=365)) -> dict:
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
def create_contract(body: ContractIn) -> dict:
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
def run_attribution(model: str = Query("time_decay"), limit: int = Query(1000, le=5000)) -> dict:
    from gamdap.growth.attribution import MODELS
    if model not in MODELS:
        raise HTTPException(400, f"지원 모델: {', '.join(MODELS)}")
    with transaction() as conn:
        rep = gs.run_attribution(conn, model=model, limit=limit)
    return {**rep, "credited_krw": str(rep["credited_krw"])}


@router.post("/pipeline/daily")
def run_daily(day: date | None = None) -> dict:
    """일일 파이프라인 — 귀속 → 집계 → 스코어링 → 부정탐지."""
    return gs.pipeline(transaction, day=day)


@router.post("/settlements/build")
def build_settlement(period_start: date, period_end: date,
                     model: str = Query("time_decay")) -> dict:
    if period_end < period_start:
        raise HTTPException(400, "기간이 올바르지 않습니다")
    with transaction() as conn:
        r = gs.build_settlement(conn, period_start=period_start, period_end=period_end,
                                model=model)
    return {**r, "gross_krw": str(r["gross_krw"]), "payable_krw": str(r["payable_krw"])}


@router.get("/settlements")
def list_settlements(partner_id: int | None = None, limit: int = Query(50, le=200)) -> list[dict]:
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
def leaderboard(days: int = Query(30, ge=1, le=365), limit: int = Query(50, le=200)) -> list[dict]:
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
def overview(days: int = Query(30, ge=1, le=365)) -> dict:
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

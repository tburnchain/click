"""수익성 계산 엔진(설계 §8, 부록 B).

핵심 수학(순수 함수, 테스트 가능):
    E_sale     : 건당 기대수익(기준통화 KRW)
    CVR_prior  : 카테고리·가격대별 사전 전환율(실측 없을 때)
    EPC        : E_sale × CVR
    demand     : native_rank 를 그룹 내 백분위로 정규화(0~1)
    epc_norm   : 로버스트 분위수 정규화(이상치 완화)
    freshness  : exp(-Δt/τ) 지수 감쇠
    score      : 100 · epc_norm^0.5 · demand^0.3 · (1-competition)^0.2 · freshness

compute_scores(conn): 활성 오퍼 전량에 대해 점수를 계산해 analytics.profitability_scores 에 UPSERT.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Connection

# 가격대별 사전 전환율(prior). 실측(포스트백) 축적 전 기본값. 튜닝 대상.
_CVR_BY_TIER = {"budget": 0.03, "mid": 0.015, "premium": 0.006, "unknown": 0.012}
# 카테고리 전환율 승수(디지털·건강 등은 전환율이 상대적으로 높음)
_CVR_CATEGORY_MULT = {
    "digital.ebook": 1.8, "digital.software": 1.6, "digital.course": 1.5, "digital": 1.6,
    "health.supplement": 1.3, "health": 1.2, "beauty": 1.2,
}
TAU_HOURS = 24.0  # 신선도 감쇠 상수(수집 주기)


# ── 순수 수학 ──────────────────────────────────────────

def price_tier(price_krw: float | None) -> str:
    if price_krw is None:
        return "unknown"
    if price_krw < 20_000:
        return "budget"
    if price_krw <= 200_000:
        return "mid"
    return "premium"


def cvr_prior(price_krw: float | None, category_slug: str | None = None) -> float:
    base = _CVR_BY_TIER[price_tier(price_krw)]
    mult = 1.0
    if category_slug:
        for key, m in _CVR_CATEGORY_MULT.items():
            if category_slug.startswith(key):
                mult = max(mult, m)
    return base * mult


def expected_earning_per_sale(
    price_krw: float | None, kind: str | None,
    rate: float | None, fixed_krw: float | None,
) -> float:
    """건당 기대수익(KRW). percent=가격×수수료율, fixed=고정액(KRW 환산)."""
    if kind == "percent" and price_krw is not None and rate is not None:
        return price_krw * rate
    if kind == "fixed" and fixed_krw is not None:
        return fixed_krw
    return 0.0


def _percentile(sorted_vals: list[float], q: float) -> float:
    """선형 보간 백분위. sorted_vals 는 오름차순."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def robust_quantile_norm(value: float, values: list[float],
                         lo_q: float = 0.05, hi_q: float = 0.95) -> float:
    """5~95 분위로 클리핑 후 min-max 정규화 → 0~1. 이상치 완화."""
    if not values:
        return 0.0
    s = sorted(values)
    p_lo = _percentile(s, lo_q)
    p_hi = _percentile(s, hi_q)
    if p_hi <= p_lo:
        return 0.5
    clipped = min(max(value, p_lo), p_hi)
    return (clipped - p_lo) / (p_hi - p_lo)


def rank_to_demand(rank: int | None, all_ranks: list[int]) -> float:
    """native_rank 를 그룹 내 수요지수로. 낮은 랭크(상위 노출)=높은 수요."""
    if rank is None or not all_ranks:
        return 0.5
    below = sum(1 for r in all_ranks if r < rank)
    pct = below / len(all_ranks)   # 0=최상위, 1=최하위
    return 1.0 - pct


def freshness_factor(hours_since: float, tau: float = TAU_HOURS) -> float:
    """exp(-Δt/τ). 데이터가 오래될수록 지수 감쇠."""
    return math.exp(-max(hours_since, 0.0) / tau)


def composite_score(
    epc_norm: float, demand: float, competition: float, freshness: float,
    w: tuple[float, float, float] = (0.5, 0.3, 0.2),
) -> float:
    """0~100 곱셈적 수익성 점수. 한 축이 0이면 전체가 낮아진다."""
    raw = (
        max(epc_norm, 0.0) ** w[0]
        * max(demand, 0.0) ** w[1]
        * max(1.0 - competition, 0.0) ** w[2]
    )
    return round(100.0 * raw * freshness, 3)


# ── 계산 잡(DB) ────────────────────────────────────────

@dataclass
class OfferRow:
    id: int
    network_id: int
    product_id: int | None
    price_krw: float | None
    commission_kind: str | None
    commission_rate: float | None
    commission_fixed_amount: float | None
    commission_currency: str | None
    native_rank: int | None
    category_slug: str | None
    fetched_at: datetime


def compute_scores(conn: Connection, now: datetime | None = None) -> int:
    """활성 오퍼 전량의 수익성 점수를 계산·UPSERT. 처리 건수 반환.

    - demand: network_id 그룹 내 native_rank 백분위(카테고리 컬럼 도입 시 category 그룹으로 승격)
    - competition: 동일 product_id 오퍼 수 기반(product 미해소면 0.5 중립)
    - epc_norm: network 그룹 내 EPC 로버스트 정규화
    """
    from gamdap.normalize.currency import CurrencyConverter

    now = now or datetime.now(UTC)
    converter = CurrencyConverter.load_latest(conn)

    rows = conn.execute(
        """
        SELECT o.id, o.network_id, o.product_id, o.price_krw,
               o.commission_kind, o.commission_rate, o.commission_fixed_amount,
               o.commission_currency, o.native_rank, o.fetched_at,
               c.slug AS category_slug
        FROM core.offers o
        LEFT JOIN core.products p ON p.id = o.product_id
        LEFT JOIN core.categories c ON c.id = p.category_id
        WHERE o.is_active
        """
    ).fetchall()
    if not rows:
        return 0

    offers = [
        OfferRow(
            id=r["id"], network_id=r["network_id"], product_id=r["product_id"],
            price_krw=float(r["price_krw"]) if r["price_krw"] is not None else None,
            commission_kind=r["commission_kind"],
            commission_rate=float(r["commission_rate"]) if r["commission_rate"] is not None else None,
            commission_fixed_amount=(
                float(r["commission_fixed_amount"])
                if r["commission_fixed_amount"] is not None else None
            ),
            commission_currency=r["commission_currency"],
            native_rank=r["native_rank"],
            category_slug=r["category_slug"],
            fetched_at=r["fetched_at"],
        )
        for r in rows
    ]

    # 그룹 통계 준비
    ranks_by_net: dict[int, list[int]] = {}
    product_counts: dict[int, int] = {}
    for o in offers:
        if o.native_rank is not None:
            ranks_by_net.setdefault(o.network_id, []).append(o.native_rank)
        if o.product_id is not None:
            product_counts[o.product_id] = product_counts.get(o.product_id, 0) + 1

    # EPC 선계산(정규화용)
    epc_by_net: dict[int, list[float]] = {}
    epc_cache: dict[int, float] = {}
    for o in offers:
        fixed_krw = None
        if o.commission_fixed_amount is not None:
            conv = converter.to_krw(Decimal(str(o.commission_fixed_amount)), o.commission_currency)
            fixed_krw = float(conv) if conv is not None else o.commission_fixed_amount
        e_sale = expected_earning_per_sale(
            o.price_krw, o.commission_kind, o.commission_rate, fixed_krw
        )
        epc = e_sale * cvr_prior(o.price_krw, o.category_slug)
        epc_cache[o.id] = epc
        epc_by_net.setdefault(o.network_id, []).append(epc)

    n = 0
    for o in offers:
        e_sale_epc = epc_cache[o.id]
        e_sale = (
            e_sale_epc / cvr_prior(o.price_krw, o.category_slug)
            if cvr_prior(o.price_krw, o.category_slug) else 0.0
        )
        demand = rank_to_demand(o.native_rank, ranks_by_net.get(o.network_id, []))
        cnt = product_counts.get(o.product_id, 1) if o.product_id else 1
        competition = min(1.0, 0.2 * (cnt - 1)) if cnt > 1 else 0.3  # 중립~경쟁
        epc_norm = robust_quantile_norm(e_sale_epc, epc_by_net.get(o.network_id, []))
        hours = (now - o.fetched_at).total_seconds() / 3600.0
        fresh = freshness_factor(hours)
        score = composite_score(epc_norm, demand, competition, fresh)

        conn.execute(
            """
            INSERT INTO analytics.profitability_scores
                (offer_id, expected_earning_per_sale, expected_epc, demand_index,
                 competition_index, freshness_factor, profitability_score, computed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (offer_id) DO UPDATE SET
                expected_earning_per_sale = EXCLUDED.expected_earning_per_sale,
                expected_epc = EXCLUDED.expected_epc,
                demand_index = EXCLUDED.demand_index,
                competition_index = EXCLUDED.competition_index,
                freshness_factor = EXCLUDED.freshness_factor,
                profitability_score = EXCLUDED.profitability_score,
                computed_at = EXCLUDED.computed_at
            """,
            (o.id, round(e_sale, 4), round(e_sale_epc, 6), round(demand, 3),
             round(competition, 3), round(fresh, 3), score, now),
        )
        n += 1
    return n

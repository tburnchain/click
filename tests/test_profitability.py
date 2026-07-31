"""수익성 계산 엔진 수학 테스트(§8, 부록 B)."""

import math

import pytest

from gamdap.analytics.profitability import (
    composite_score,
    cvr_prior,
    expected_earning_per_sale,
    freshness_factor,
    price_tier,
    rank_to_demand,
    robust_quantile_norm,
)


def test_e_sale_percent():
    # 130만원 × 3% = 39,000
    assert expected_earning_per_sale(1_300_000, "percent", 0.03, None) == pytest.approx(39_000)


def test_e_sale_fixed():
    assert expected_earning_per_sale(50_000, "fixed", None, 7500) == 7500


def test_e_sale_low_commission_high_price_beats_high_commission_low_price():
    # 15% × 5,000 = 750  vs  3% × 1,300,000 = 39,000  → 후자가 압도
    low = expected_earning_per_sale(5_000, "percent", 0.15, None)
    high = expected_earning_per_sale(1_300_000, "percent", 0.03, None)
    assert high > low * 10


def test_price_tier():
    assert price_tier(5_000) == "budget"
    assert price_tier(100_000) == "mid"
    assert price_tier(500_000) == "premium"
    assert price_tier(None) == "unknown"


def test_cvr_prior_category_boost():
    # 디지털은 같은 가격대라도 전환율 승수가 높다
    assert cvr_prior(30_000, "digital.ebook") > cvr_prior(30_000, None)


def test_rank_to_demand_top_is_high():
    ranks = [1, 2, 3, 10, 50]
    assert rank_to_demand(1, ranks) == 1.0        # 최상위
    assert rank_to_demand(50, ranks) < rank_to_demand(1, ranks)


def test_rank_to_demand_missing_is_neutral():
    assert rank_to_demand(None, [1, 2, 3]) == 0.5


def test_robust_norm_bounds():
    vals = [1, 2, 3, 4, 5, 100]  # 100 은 이상치
    n_low = robust_quantile_norm(1, vals)
    n_high = robust_quantile_norm(100, vals)
    assert 0.0 <= n_low <= 1.0
    assert n_high == pytest.approx(1.0)  # 상위 클리핑
    assert n_high > n_low


def test_freshness_decay():
    assert freshness_factor(0) == 1.0
    assert freshness_factor(24) == pytest.approx(math.exp(-1), rel=1e-6)
    assert freshness_factor(48) < freshness_factor(24)


def test_composite_zero_axis_collapses():
    # 수요가 0이면(곱셈적) 점수가 붕괴 → 함정 상품 배제
    high = composite_score(1.0, 1.0, 0.0, 1.0)
    trap = composite_score(1.0, 0.0, 0.0, 1.0)  # EPC 최고지만 수요 0
    assert trap < high
    assert trap == 0.0


def test_composite_range():
    s = composite_score(1.0, 1.0, 0.0, 1.0)
    assert s == pytest.approx(100.0)
    s2 = composite_score(0.5, 0.5, 0.5, 1.0)
    assert 0 < s2 < 100


def test_competition_penalty():
    low_comp = composite_score(0.8, 0.8, 0.1, 1.0)
    high_comp = composite_score(0.8, 0.8, 0.9, 1.0)
    assert low_comp > high_comp

"""분석: 수익성 계산 엔진(§8)."""

from gamdap.analytics.profitability import (
    composite_score,
    compute_scores,
    cvr_prior,
    expected_earning_per_sale,
    freshness_factor,
    rank_to_demand,
    robust_quantile_norm,
)

__all__ = [
    "expected_earning_per_sale",
    "cvr_prior",
    "rank_to_demand",
    "robust_quantile_norm",
    "freshness_factor",
    "composite_score",
    "compute_scores",
]

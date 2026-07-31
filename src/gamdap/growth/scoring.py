"""파트너·인플루언서 성과 스코어링 — 소표본 왜곡을 제거한 순위 산정.

왜 단순 평균이 위험한가: 클릭 3회에 전환 1회면 CVR 33%다. 이 값으로 순위를 매기면
표본이 적은 파트너가 항상 상위를 차지하고, 실제로는 운(noise)이었던 성과에 최고
등급과 최고 수수료가 배정된다. 위탁 확장 모델에서 이는 곧 손실이다.

적용 수학
  · 경험적 베이즈(Beta-Binomial 켤레): 전체 모집단의 사전분포로 개별 추정치를
    수축(shrinkage)시킨다. 표본이 커질수록 자기 데이터로 수렴.
  · Wilson score 구간: 이항비율의 신뢰구간 하한으로 랭킹 → '운 좋은 소표본' 배제.
  · 로그 정규화: 팔로워·클릭처럼 멱법칙 분포인 값은 log1p 후 0~100 스케일.
  · 가중 기하평균: 종합점수는 산술평균이 아닌 기하평균 — 한 축이 0에 가까우면
    종합도 낮아진다(모든 축이 고르게 좋아야 상위). 사기점수는 역가중.
  · 히스테리시스 티어링: 승급/강등 임계를 분리해 경계에서의 등급 진동을 막는다.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "wilson_lower_bound", "empirical_bayes_prior", "shrink_rate", "shrink_mean",
    "log_scale_score", "weighted_geometric_mean", "TIERS", "assign_tier",
    "PartnerStats", "score_partner",
]

# 등급: (코드, 승급 임계점수, 강등 임계점수) — 승급 > 강등 이어야 히스테리시스 성립
TIERS: tuple[tuple[str, float, float], ...] = (
    ("diamond",  90.0, 85.0),
    ("platinum", 75.0, 70.0),
    ("gold",     60.0, 55.0),
    ("silver",   40.0, 35.0),
    ("bronze",    0.0,  0.0),
)
_TIER_ORDER = {code: i for i, (code, _, _) in enumerate(reversed(TIERS))}  # bronze=0 … diamond=4


def wilson_lower_bound(successes: int, trials: int, *, z: float = 1.96) -> float:
    """이항비율의 Wilson 신뢰구간 하한(기본 95%).

    표본이 작을수록 하한이 크게 내려가 과대평가를 자동으로 억제한다.
    trials=0 이면 0.0(정보 없음 = 최하위).
    """
    if trials <= 0:
        return 0.0
    p = successes / trials
    z2 = z * z
    denom = 1.0 + z2 / trials
    center = p + z2 / (2 * trials)
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * trials)) / trials)
    return max(0.0, (center - margin) / denom)


def empirical_bayes_prior(observations: Sequence[tuple[int, int]]) -> tuple[float, float]:
    """모집단에서 Beta 사전분포 (alpha, beta) 를 적률법으로 추정.

    observations: [(성공수, 시행수)]
    표본이 부족하면 무정보 사전(1,1) — Laplace 평활과 동일하게 동작.
    """
    rates = [(s / n) for s, n in observations if n > 0]
    if len(rates) < 2:
        return 1.0, 1.0
    mean = sum(rates) / len(rates)
    var = sum((r - mean) ** 2 for r in rates) / (len(rates) - 1)
    if var <= 1e-12 or mean <= 0 or mean >= 1:
        return 1.0, 1.0
    # 적률법: mean=a/(a+b), var=ab/((a+b)^2(a+b+1)) → 공통 크기 k=a+b
    k = mean * (1 - mean) / var - 1
    if k <= 0:
        return 1.0, 1.0
    k = min(k, 10_000.0)   # 과도한 수축 방지 상한
    return mean * k, (1 - mean) * k


def shrink_rate(successes: int, trials: int, alpha: float, beta: float) -> float:
    """Beta-Binomial 사후평균 = (성공+α)/(시행+α+β).

    시행이 적으면 사전평균 α/(α+β) 쪽으로, 많아지면 관측비율로 수렴한다.
    """
    denom = trials + alpha + beta
    return (successes + alpha) / denom if denom > 0 else 0.0


def shrink_mean(value_sum: float, count: int, prior_mean: float,
                prior_weight: float = 30.0) -> float:
    """연속값(EPC 등)의 수축 평균 = (합 + 사전평균×사전무게) / (건수 + 사전무게).

    prior_weight 는 '사전분포가 몇 건의 관측에 해당하는가'. 30 은 실무에서
    안정과 반응성의 균형점으로 쓰이는 값이다.
    """
    denom = count + prior_weight
    return (value_sum + prior_mean * prior_weight) / denom if denom > 0 else prior_mean


def log_scale_score(value: float, *, p95: float, cap: float = 100.0) -> float:
    """멱법칙 분포 값(팔로워·클릭)을 0~100 으로. p95 를 100 에 대응시킨다."""
    if value <= 0 or p95 <= 0:
        return 0.0
    score = math.log1p(value) / math.log1p(p95) * cap
    return max(0.0, min(cap, score))


def weighted_geometric_mean(pairs: Sequence[tuple[float, float]], *, floor: float = 1.0) -> float:
    """가중 기하평균. pairs=[(값0~100, 가중치)].

    한 축이 0 이면 전체가 0 이 되는 것을 막기 위해 floor 로 하한을 둔다.
    산술평균과 달리 '약한 고리'가 종합을 끌어내려, 고른 성과를 요구한다.
    """
    num = 0.0
    wsum = 0.0
    for value, weight in pairs:
        if weight <= 0:
            continue
        v = max(floor, min(100.0, value))
        num += weight * math.log(v)
        wsum += weight
    if wsum <= 0:
        return 0.0
    return math.exp(num / wsum)


def assign_tier(score: float, current: str | None = None) -> str:
    """히스테리시스 티어 배정.

    현재 등급이 있으면 '강등 임계' 아래로 떨어져야 내려가고, 올라갈 때는
    '승급 임계'를 넘어야 한다. 경계값 근처에서 매일 등급이 바뀌는 현상을 막는다.
    """
    # 승급 판정: 위에서부터 승급 임계를 만족하는 최고 등급
    promoted = "bronze"
    for code, up, _down in TIERS:
        if score >= up:
            promoted = code
            break
    if not current or current not in _TIER_ORDER:
        return promoted
    if _TIER_ORDER[promoted] > _TIER_ORDER[current]:
        return promoted   # 승급은 즉시
    # 유지/강등: 현재 등급의 강등 임계를 지키면 유지
    down = next((d for c, _u, d in TIERS if c == current), 0.0)
    if score >= down:
        return current
    return promoted


@dataclass(frozen=True)
class PartnerStats:
    """스코어링 입력. 기간 집계값."""

    partner_id: int
    clicks: int = 0
    conversions: int = 0
    revenue_krw: float = 0.0
    unique_visitors: int = 0
    followers: int = 0
    bot_click_ratio: float = 0.0      # 0~1
    ip_concentration: float = 0.0     # 0~1 (상위 IP 편중도)
    active_days: int = 0


@dataclass(frozen=True)
class PartnerScore:
    partner_id: int
    reach: float
    engagement: float
    conversion: float
    fraud: float
    composite: float
    cvr_shrunk: float
    cvr_lower: float
    epc_shrunk: float
    tier: str


def score_partner(stats: PartnerStats, *, prior_ab: tuple[float, float],
                  prior_epc: float, p95_clicks: float, p95_followers: float,
                  current_tier: str | None = None) -> PartnerScore:
    """단일 파트너 종합 스코어링.

    prior_ab / prior_epc / p95_* 는 모집단에서 미리 구한 값(cohort_priors 참조).
    """
    alpha, beta = prior_ab
    # DB 집계값이 Decimal 로 올 수 있어 명시적으로 정규화한다.
    clicks, convs = int(stats.clicks), int(stats.conversions)
    revenue = float(stats.revenue_krw)
    cvr_shrunk = shrink_rate(convs, clicks, alpha, beta)
    cvr_lower = wilson_lower_bound(convs, clicks)
    epc_shrunk = shrink_mean(revenue, clicks, prior_epc)

    # 도달: 클릭량과 팔로워의 로그 스케일 결합
    reach = 0.6 * log_scale_score(float(clicks), p95=p95_clicks) \
        + 0.4 * log_scale_score(float(stats.followers), p95=p95_followers)

    # 참여: 순방문자 대비 클릭(재방문·관여) + 활동 지속성
    uv = int(stats.unique_visitors)
    depth = (clicks / uv) if uv > 0 else 0.0
    engagement = min(100.0, 50.0 * min(depth, 2.0) + 50.0 * min(int(stats.active_days) / 30.0, 1.0))

    # 전환: Wilson 하한 기반(소표본 배제). 사전분포 대비 상대 성과로 스케일.
    prior_cvr = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.01
    rel = (cvr_lower / prior_cvr) if prior_cvr > 0 else 0.0
    conversion = max(0.0, min(100.0, 50.0 * rel))

    # 사기: 봇비율·IP편중을 0~100 위험도로(높을수록 위험)
    fraud = min(100.0, 100.0 * (0.6 * stats.bot_click_ratio + 0.4 * stats.ip_concentration))

    # 종합: 기하평균 + 사기 페널티(승수)
    base = weighted_geometric_mean([
        (reach, 0.25), (engagement, 0.20), (conversion, 0.55),
    ])
    composite = base * (1.0 - min(0.9, fraud / 100.0))

    return PartnerScore(
        partner_id=stats.partner_id,
        reach=round(reach, 2), engagement=round(engagement, 2),
        conversion=round(conversion, 2), fraud=round(fraud, 2),
        composite=round(composite, 2),
        cvr_shrunk=cvr_shrunk, cvr_lower=cvr_lower, epc_shrunk=epc_shrunk,
        tier=assign_tier(composite, current_tier),
    )


def cohort_priors(all_stats: Sequence[PartnerStats]) -> dict:
    """모집단에서 사전분포·백분위를 산출(스코어링 전 1회 실행)."""
    # DB 는 SUM 을 Decimal 로 돌려주므로 float 로 통일한다(혼합 연산 TypeError 방지).
    obs = [(int(s.conversions), int(s.clicks)) for s in all_stats if s.clicks > 0]
    alpha, beta = empirical_bayes_prior(obs)
    total_clicks = float(sum(int(s.clicks) for s in all_stats))
    total_rev = float(sum(float(s.revenue_krw) for s in all_stats))
    prior_epc = (total_rev / total_clicks) if total_clicks > 0 else 0.0

    def _p95(values: list[float]) -> float:
        if not values:
            return 1.0
        vs = sorted(values)
        idx = min(len(vs) - 1, int(0.95 * (len(vs) - 1)))
        return max(vs[idx], 1.0)

    return {
        "prior_ab": (alpha, beta),
        "prior_epc": prior_epc,
        "p95_clicks": _p95([float(s.clicks) for s in all_stats]),
        "p95_followers": _p95([float(s.followers) for s in all_stats]),
    }

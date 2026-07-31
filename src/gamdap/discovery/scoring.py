"""발견 후보 스코어링(§16.4) + UCB1 탐사 정책(§16.3).

candidate_score: 곱셈 게이트 — 공식/애그리게이터 원천이 없거나 약관 위반이면 0점.
                 (발견해도 신뢰 못 얻는 네트워크를 자동 탈락시킨다.)
ucb_score/select_arm: 크롤 예산을 착취(exploitation)와 탐험(exploration) 사이에서 최적 배분.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@dataclass(frozen=True)
class CandidateSignals:
    source_trust: float          # 0~1 (애그리게이터=높음)
    has_official_api: bool
    has_product_feed: bool
    terms_scrape_allowed: bool
    category_fit: float          # 0~1
    commission_viability: float  # 0~1
    country_priority: float      # 0~1


def candidate_score(
    s: CandidateSignals, *, w1: float = 1.4, w2: float = 1.1, w3: float = 0.8,
) -> float:
    """0~100. 곱셈 게이트로 원천/약관 결격 시 0.

    score = 100 · trust
          · 𝟙[official_api ∨ feed]          (데이터 원천 확보 가능성)
          · 𝟙[scrape_allowed ∨ official_api] (약관 적합)
          · sigmoid(w1·fit + w2·commission + w3·country)
    """
    origin_gate = 1.0 if (s.has_official_api or s.has_product_feed) else 0.0
    terms_gate = 1.0 if (s.terms_scrape_allowed or s.has_official_api) else 0.0
    if origin_gate == 0.0 or terms_gate == 0.0:
        return 0.0
    quality = _sigmoid(
        w1 * s.category_fit + w2 * s.commission_viability + w3 * s.country_priority - 1.5
    )
    return round(100.0 * s.source_trust * origin_gate * terms_gate * quality, 3)


def ucb_score(reward_mean: float, pulls: int, total_pulls: int, c: float = 1.0) -> float:
    """UCB1: R̄ + c·√(2·ln N / n). 미탐색(n=0) arm 은 +∞ 로 우선 탐험."""
    if pulls <= 0:
        return math.inf
    if total_pulls <= 0:
        return reward_mean
    return reward_mean + c * math.sqrt(2.0 * math.log(total_pulls) / pulls)


@dataclass
class Arm:
    key: str
    reward_mean: float
    pulls: int


def select_arm(arms: list[Arm], c: float = 1.0) -> Arm | None:
    """UCB 최댓값 arm 선택. 동점 시 pull 이 적은 쪽(더 탐험 필요)."""
    if not arms:
        return None
    total = sum(a.pulls for a in arms)
    return max(
        arms,
        key=lambda a: (ucb_score(a.reward_mean, a.pulls, total, c), -a.pulls),
    )


def update_arm(reward_sum: float, pulls: int, new_reward: float) -> tuple[float, int, float]:
    """온라인 평균 갱신. Returns (reward_sum, pulls, reward_mean)."""
    reward_sum += new_reward
    pulls += 1
    return reward_sum, pulls, reward_sum / pulls

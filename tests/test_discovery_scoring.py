"""발견 후보 스코어(§16.4) + UCB 탐사(§16.3) 테스트."""

import math

from gamdap.discovery.scoring import (
    Arm,
    CandidateSignals,
    candidate_score,
    select_arm,
    ucb_score,
    update_arm,
)


def _sig(**kw) -> CandidateSignals:
    base = dict(
        source_trust=0.9, has_official_api=True, has_product_feed=False,
        terms_scrape_allowed=False, category_fit=0.8,
        commission_viability=0.7, country_priority=0.6,
    )
    base.update(kw)
    return CandidateSignals(**base)


def test_official_api_scores_positive():
    assert candidate_score(_sig()) > 0


def test_no_origin_is_zero():
    # 공식 API도 피드도 없으면 0점(곱셈 게이트)
    assert candidate_score(_sig(has_official_api=False, has_product_feed=False)) == 0.0


def test_terms_violation_is_zero():
    # 스크래핑 불가 + 공식 API 없음(피드만) → 약관 게이트 0
    s = _sig(has_official_api=False, has_product_feed=True, terms_scrape_allowed=False)
    assert candidate_score(s) == 0.0


def test_feed_with_scrape_allowed_passes():
    s = _sig(has_official_api=False, has_product_feed=True, terms_scrape_allowed=True)
    assert candidate_score(s) > 0


def test_higher_trust_scores_higher():
    assert candidate_score(_sig(source_trust=0.95)) > candidate_score(_sig(source_trust=0.5))


def test_ucb_unpulled_is_infinite():
    assert ucb_score(0.0, pulls=0, total_pulls=10) == math.inf


def test_ucb_exploration_bonus():
    # 같은 평균이면 덜 뽑힌 arm 의 UCB 가 더 높다
    high_pull = ucb_score(0.5, pulls=100, total_pulls=1000)
    low_pull = ucb_score(0.5, pulls=5, total_pulls=1000)
    assert low_pull > high_pull


def test_select_arm_prefers_unexplored():
    arms = [Arm("a", 0.9, 50), Arm("b_new", 0.0, 0)]
    assert select_arm(arms).key == "b_new"  # 미탐색 우선


def test_update_arm_online_mean():
    rs, n, mean = update_arm(0.0, 0, 1.0)
    rs, n, mean = update_arm(rs, n, 3.0)
    assert n == 2
    assert mean == 2.0

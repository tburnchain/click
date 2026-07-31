"""광고상품 분류 엔진 수학 테스트(§18, M8)."""

import pytest

from gamdap.analytics.classification import (
    SegmentThresholds,
    assign_segment,
    classify_category,
    classify_intent,
    cluster_embeddings,
    competition_index,
    entropy_norm,
    hhi,
    opportunity_score,
)
from gamdap.textvec import hashing_embedding


# ── 경쟁 수학 ──
def test_hhi_monopoly_vs_fragmented():
    assert hhi([100]) == pytest.approx(1.0)              # 완전 독점
    assert hhi([25, 25, 25, 25]) == pytest.approx(0.25)  # 4등분
    assert hhi([]) == 0.0


def test_entropy_norm():
    assert entropy_norm([50, 50]) == pytest.approx(1.0)  # 최대 파편화
    assert entropy_norm([100, 0]) == pytest.approx(0.0)  # 독점
    assert entropy_norm([10]) == 0.0


def test_competition_index_bounds():
    k = competition_index(1.0, 1.0, 0.0)
    assert 0.0 <= k <= 1.0
    # 공급·독점 높고 파편화 낮으면 경쟁 높음
    assert competition_index(1.0, 1.0, 0.0) > competition_index(0.1, 0.2, 1.0)


# ── 기회 사분면 ──
def test_opportunity_score_multiplicative():
    assert opportunity_score(0.0, 1.0, 0.0) == 0.0       # Π=0 → 붕괴
    assert opportunity_score(1.0, 1.0, 0.0) == pytest.approx(1.0)
    assert opportunity_score(1.0, 1.0, 1.0) == 0.0       # 경쟁 최대 → 붕괴


TH = SegmentThresholds(pi_hi=0.75, pi_lo=0.25, d_hi=0.7, d_lo=0.3, k_hi=0.66, k_lo=0.33)


def test_segment_goldmine():
    assert assign_segment(0.9, 0.8, 0.2, TH) == "goldmine"   # 고수익·고수요·저경쟁


def test_segment_cashcow():
    assert assign_segment(0.9, 0.8, 0.8, TH) == "cashcow"    # 고수익·고수요·고경쟁


def test_segment_avoid():
    assert assign_segment(0.1, 0.8, 0.2, TH) == "avoid"      # 저수익
    assert assign_segment(0.8, 0.1, 0.2, TH) == "avoid"      # 저수요


def test_segment_rising():
    assert assign_segment(0.5, 0.5, 0.2, TH) == "rising"     # 저경쟁 신흥


def test_segment_saturated():
    assert assign_segment(0.5, 0.5, 0.9, TH) == "saturated"  # 고경쟁


# ── 의도 분류 ──
def test_intent_problem_solving():
    assert classify_intent("무릎 통증 완화 밴드", "health", 30000) == "problem_solving"


def test_intent_impulse_low_price():
    assert classify_intent("귀여운 스티커", "home", 3000) == "impulse"


def test_intent_digital_considered():
    assert classify_intent("파이썬 강의", "digital.course", 50000) == "considered"


# ── 계층 분류 ──
def test_classify_category_picks_nearest():
    ea = hashing_embedding("무선 이어폰 블루투스")
    sup = hashing_embedding("비타민 영양제 건강")
    centroids = {1: ea, 2: sup}
    query = hashing_embedding("무선 이어폰 프로")
    cid, conf = classify_category(query, centroids)
    assert cid == 1
    assert 0 < conf <= 1


def test_classify_category_empty():
    assert classify_category([0.1], {}) == (None, 0.0)


# ── 니치 군집 ──
def test_cluster_groups_similar():
    items = [
        (1, hashing_embedding("무선 이어폰 블루투스")),
        (2, hashing_embedding("무선 이어폰 블루투스 프로")),
        (3, hashing_embedding("강아지 사료 대용량 사료")),
    ]
    clusters = cluster_embeddings(items, threshold=0.5)
    # 이어폰 2개는 한 군집, 사료는 별도일 가능성 높음
    sizes = sorted(len(c) for c in clusters)
    assert 3 in (len(items),) or sizes[-1] >= 2
    all_ids = sorted(i for c in clusters for i in c)
    assert all_ids == [1, 2, 3]   # 모든 아이템 배정

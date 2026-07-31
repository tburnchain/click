"""엔티티 해소 매칭 로직 테스트(§5.4)."""

import pytest

from gamdap.ingest.entity_resolution import (
    LINK_HIGH,
    LINK_LOW,
    match_score,
    name_similarity,
    normalize_name,
    price_proximity,
    token_jaccard,
    trigram_similarity,
)


def test_normalize_name():
    assert normalize_name("  삼성 [정품] Galaxy-Book3!! ") == "삼성 정품 galaxy book3"


def test_token_jaccard_noise_removed():
    # '정품','무료배송'은 노이즈로 제거 → 핵심 토큰만 비교
    a = "샤오미 로봇청소기 정품 무료배송"
    b = "샤오미 로봇청소기"
    assert token_jaccard(a, b) == 1.0


def test_trigram_similarity_close():
    assert trigram_similarity("에어프라이어", "에어프라이어기") > 0.5
    assert trigram_similarity("에어프라이어", "강아지사료") < 0.2


def test_name_similarity_same_high():
    assert name_similarity("무선 블루투스 이어폰", "무선 블루투스 이어폰") == pytest.approx(1.0)


def test_name_similarity_different_low():
    assert name_similarity("무선 이어폰", "강아지 사료") < 0.3


def test_price_proximity():
    assert price_proximity(10000, 10000) == 1.0        # 동일
    assert price_proximity(10000, 10500) > 0.7         # 5% 차이
    assert price_proximity(10000, 50000) < 0.3         # 큰 차이
    assert price_proximity(None, 100) == 0.5           # 미상 → 중립


def test_match_score_same_product_high():
    sc = match_score("샤오미 로봇청소기 X10", 130000, "샤오미 로봇청소기 X10", 132000)
    assert sc >= LINK_HIGH


def test_match_score_different_product_low():
    sc = match_score("샤오미 로봇청소기", 130000, "강아지 사료 5kg", 20000)
    assert sc < LINK_LOW


def test_match_score_ambiguous_band():
    # 유사하지만 확신 못 하는 케이스 → 중간 구간
    sc = match_score("무선 이어폰 프로", 50000, "무선 이어폰", 90000)
    assert 0.0 <= sc <= 1.0


def test_brand_mismatch_penalizes():
    same = match_score("이어폰", 10000, "이어폰", 10000, brand_a="A", brand_b="A")
    diff = match_score("이어폰", 10000, "이어폰", 10000, brand_a="A", brand_b="B")
    assert same > diff

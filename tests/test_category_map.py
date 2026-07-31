"""카테고리 매핑 규칙 테스트(§5.3)."""

import pytest

from gamdap.normalize.category_map import map_category


@pytest.mark.parametrize("raw,slug", [
    ("가전", "electronics"),
    ("주방가전", "electronics.appliance"),
    ("노트북", "electronics.computer"),
    ("휴대폰", "electronics.mobile"),
    ("뷰티", "beauty"),
    ("스킨케어", "beauty.skincare"),
    ("영양제", "health.supplement"),
    ("건강식품", "health"),  # '영양제/supplement' 미포함 → '건강' 규칙이 health 로 매핑
    ("디지털", "digital"),
    ("온라인 강의", "digital.course"),
    ("패션의류", "fashion"),
    ("Electronics", "electronics"),
    ("Beauty & Cosmetic", "beauty"),
])
def test_known_categories(raw, slug):
    got, conf = map_category(raw)
    assert got == slug
    assert conf > 0


def test_specific_before_general():
    # '주방가전' 은 일반 '가전'(electronics)보다 구체 규칙(appliance)이 먼저 잡혀야 한다
    assert map_category("주방가전")[0] == "electronics.appliance"


def test_exact_match_high_confidence():
    slug, conf = map_category("가전")
    assert conf == 1.0  # 정확 일치


def test_partial_match_lower_confidence():
    slug, conf = map_category("삼성 가전 제품")
    assert slug == "electronics"
    assert conf == 0.85


def test_unmapped_returns_none():
    slug, conf = map_category("애매한분류xyz")
    assert slug is None
    assert conf == 0.0


def test_empty():
    assert map_category("") == (None, 0.0)
    assert map_category(None) == (None, 0.0)

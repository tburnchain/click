"""카테고리 매핑(§5.3): 네트워크 원본 카테고리 → 통합 택소노미 slug.

1차 규칙 사전(키워드→slug). 매핑 실패는 None(리뷰 큐 대상).
DB 연동: network_categories 에 학습·캐시.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Connection

# 키워드(부분일치, 소문자) → 통합 slug. 더 구체적인 것을 앞에 둔다(먼저 매칭).
_RULES: list[tuple[tuple[str, ...], str]] = [
    (("주방", "생활가전", "appliance", "kitchen"), "electronics.appliance"),
    (("노트북", "컴퓨터", "computer", "laptop", "pc"), "electronics.computer"),
    (("휴대폰", "모바일", "태블릿", "phone", "mobile", "tablet"), "electronics.mobile"),
    (("가전", "전자", "electronics", "digital device"), "electronics"),
    (("스킨케어", "skincare", "스킨"), "beauty.skincare"),
    (("메이크업", "makeup", "코스메틱"), "beauty.makeup"),
    (("뷰티", "화장품", "beauty", "cosmetic"), "beauty"),
    (("영양제", "보충제", "supplement", "vitamin"), "health.supplement"),
    (("건강", "헬스", "health", "wellness"), "health"),
    (("전자책", "ebook", "e-book"), "digital.ebook"),
    (("소프트웨어", "software", "saas", "app"), "digital.software"),
    (("강의", "course", "class", "학습"), "digital.course"),
    (("디지털", "digital"), "digital"),
    (("패션", "의류", "fashion", "apparel", "clothing", "shoes", "신발"), "fashion"),
    (("가구", "리빙", "home", "furniture", "living"), "home"),
    (("식품", "그로서리", "food", "grocery", "간식"), "food"),
    (("유아", "출산", "baby", "kids"), "baby"),
    (("스포츠", "레저", "sports", "outdoor", "fitness"), "sports"),
    (("반려", "펫", "pet", "dog", "cat"), "pet"),
]


def map_category(raw_name: str | None) -> tuple[str | None, float]:
    """원본 카테고리명 → (통합 slug | None, confidence). 순수 함수."""
    if not raw_name or not raw_name.strip():
        return None, 0.0
    text = raw_name.strip().lower()
    for keywords, slug in _RULES:
        for kw in keywords:
            if kw in text:
                # 정확 일치는 1.0, 부분 일치는 0.85
                conf = 1.0 if kw == text else 0.85
                return slug, conf
    return None, 0.0


def resolve_category_id(conn: Connection, network_id: int, raw_name: str | None) -> int | None:
    """원본 카테고리를 통합 category_id 로 해소. network_categories 에 캐시.

    캐시 히트 시 그대로 반환, 미스 시 규칙 매핑 후 저장(미매핑도 기록 → 리뷰 큐).
    """
    if not raw_name:
        return None

    cached = conn.execute(
        "SELECT category_id FROM core.network_categories "
        "WHERE network_id = %s AND raw_name = %s",
        (network_id, raw_name),
    ).fetchone()
    if cached is not None:
        return cached["category_id"]

    slug, conf = map_category(raw_name)
    category_id: int | None = None
    if slug is not None:
        row = conn.execute(
            "SELECT id FROM core.categories WHERE slug = %s", (slug,)
        ).fetchone()
        category_id = row["id"] if row else None

    conn.execute(
        "INSERT INTO core.network_categories "
        "(network_id, raw_name, category_id, mapping_confidence, mapped_by) "
        "VALUES (%s, %s, %s, %s, 'rule') "
        "ON CONFLICT (network_id, raw_name) DO NOTHING",
        (network_id, raw_name, category_id, conf),
    )
    return category_id

"""엔티티 해소(§5.4) — 네트워크 간 동일 상품을 통합 products 로 연결.

전략:
  강한 키(GTIN/모델) 일치 → 즉시 병합(현재 오퍼에 GTIN 없음, 후속 확장 대비)
  약한 키(이름 트라이그램 유사도 + 가격 근접) → 임계 이상이면 링크, 애매하면 리뷰 큐(보수적)
  매칭 없음 → 신규 상품 생성 후 링크

순수 매칭 함수(테스트 가능)와 DB 잡(resolve_products)을 분리.
자동 오병합은 데이터 오염이므로 임계는 보수적으로.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gamdap.logging import get_logger

if TYPE_CHECKING:
    from psycopg import Connection

log = get_logger("entity_resolution")

# 임계값(튜닝 대상)
LINK_HIGH = 0.72     # 이 이상이면 자동 링크
LINK_LOW = 0.45      # 이 구간은 애매 → 리뷰 큐(자동 병합 안 함)

_PUNCT = re.compile(r"[^0-9a-z가-힣\s]")
_WS = re.compile(r"\s+")
# 매칭 노이즈(브랜드 무관 흔한 수식어)
_NOISE = {"정품", "무료배송", "당일발송", "best", "new", "sale", "official", "set", "세트"}


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    s = _PUNCT.sub(" ", name.lower())
    s = _WS.sub(" ", s).strip()
    return s


def tokens(name: str | None) -> list[str]:
    return [t for t in normalize_name(name).split() if t and t not in _NOISE]


def token_jaccard(a: str, b: str) -> float:
    sa, sb = set(tokens(a)), set(tokens(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _trigrams(s: str) -> set[str]:
    s = normalize_name(s).replace(" ", "")
    if len(s) < 3:
        return {s} if s else set()
    return {s[i:i + 3] for i in range(len(s) - 2)}


def trigram_similarity(a: str, b: str) -> float:
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def name_similarity(a: str, b: str) -> float:
    """토큰 자카드와 트라이그램 유사도의 블렌드(0~1)."""
    return 0.5 * token_jaccard(a, b) + 0.5 * trigram_similarity(a, b)


def price_proximity(p1: float | None, p2: float | None, tol: float = 0.15) -> float:
    """가격 근접(0~1). 둘 중 하나라도 없으면 중립 0.5."""
    if p1 is None or p2 is None or p1 <= 0 or p2 <= 0:
        return 0.5
    ratio = abs(p1 - p2) / max(p1, p2)
    if ratio <= tol:
        return 1.0 - ratio / tol * 0.5   # tol 이내면 0.5~1.0
    return max(0.0, 0.5 - (ratio - tol))


def match_score(name_a: str, price_a: float | None,
                name_b: str, price_b: float | None,
                brand_a: str | None = None, brand_b: str | None = None) -> float:
    """상품 일치 점수(0~1). 이름 0.7 + 가격 0.2 + 브랜드 0.1."""
    name = name_similarity(name_a, name_b)
    price = price_proximity(price_a, price_b)
    brand = 0.5
    if brand_a and brand_b:
        brand = 1.0 if normalize_name(brand_a) == normalize_name(brand_b) else 0.0
    return 0.7 * name + 0.2 * price + 0.1 * brand


@dataclass
class ResolveStats:
    linked: int = 0
    created: int = 0
    review: int = 0


def resolve_products(conn: Connection, batch: int = 500) -> ResolveStats:
    """미연결 활성 오퍼를 통합 상품에 연결. 신규는 상품 생성. 통계 반환."""
    from gamdap.normalize.category_map import resolve_category_id

    stats = ResolveStats()
    offers = conn.execute(
        "SELECT id, network_id, title, price_krw, thumbnail_url, raw_category "
        "FROM core.offers "
        "WHERE is_active AND product_id IS NULL "
        "ORDER BY id LIMIT %s",
        (batch,),
    ).fetchall()

    for o in offers:
        title = o["title"]
        price = float(o["price_krw"]) if o["price_krw"] is not None else None

        # 후보 검색: pg_trgm 유사도 상위 5
        cands = conn.execute(
            "SELECT id, canonical_name, brand, category_id "
            "FROM core.products "
            "WHERE similarity(canonical_name, %s) > 0.3 "
            "ORDER BY similarity(canonical_name, %s) DESC LIMIT 5",
            (title, title),
        ).fetchall()

        best_id, best_score = None, 0.0
        for c in cands:
            sc = match_score(title, price, c["canonical_name"], None, None, c["brand"])
            if sc > best_score:
                best_id, best_score = c["id"], sc

        if best_id is not None and best_score >= LINK_HIGH:
            conn.execute("UPDATE core.offers SET product_id=%s WHERE id=%s", (best_id, o["id"]))
            stats.linked += 1
        elif best_id is not None and best_score >= LINK_LOW:
            # 애매 → 자동 병합 금지, 리뷰 큐로
            conn.execute("UPDATE core.offers SET needs_review=TRUE WHERE id=%s", (o["id"],))
            stats.review += 1
        else:
            category_id = resolve_category_id(conn, o["network_id"], o["raw_category"])
            new = conn.execute(
                "INSERT INTO core.products (canonical_name, category_id, primary_image_url) "
                "VALUES (%s,%s,%s) RETURNING id",
                (title, category_id, o["thumbnail_url"]),
            ).fetchone()
            conn.execute("UPDATE core.offers SET product_id=%s WHERE id=%s", (new["id"], o["id"]))
            stats.created += 1

    log.info("entity.resolve_done", linked=stats.linked, created=stats.created, review=stats.review)
    return stats

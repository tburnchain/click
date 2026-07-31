"""공개페이지 크롤러(Mode A) + LUXEVIA 피드 수집(Mode B) 검증."""

from decimal import Decimal

import pytest

from gamdap.connectors.webcrawler import extract_product
from gamdap.ingest import product_feed as pf


# ── Mode A: 추출 ──
def test_extract_jsonld_product():
    html = '''<html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","name":"루이비통 백",
     "brand":{"@type":"Brand","name":"Louis Vuitton"},"sku":"M12345",
     "image":["https://cdn/x.jpg"],
     "offers":{"@type":"Offer","price":"2500000","priceCurrency":"KRW"}}
    </script></head><body></body></html>'''
    p = extract_product(html, "https://shop/p/1")
    assert p["name"] == "루이비통 백" and p["brand"] == "Louis Vuitton"
    assert p["price"] == Decimal("2500000") and p["currency"] == "KRW"
    assert p["sku"] == "M12345"


def test_extract_opengraph():
    html = ('<meta property="og:title" content="구찌 지갑">'
            '<meta property="product:price:amount" content="890000">'
            '<meta property="product:price:currency" content="KRW">'
            '<meta property="og:image" content="https://cdn/g.jpg">')
    p = extract_product(html, "https://shop/p/2")
    assert p["name"] == "구찌 지갑" and p["price"] == Decimal("890000") and p["currency"] == "KRW"


def test_extract_heuristic_price_class():
    html = '<h1>A Light in the Attic</h1><p class="price_color">£51.77</p>'
    p = extract_product(html, "https://books/p/3")
    assert p["name"] == "A Light in the Attic"
    assert p["price"] == Decimal("51.77") and p["currency"] == "GBP"


def test_extract_none_on_junk():
    assert extract_product("<html><body>no product</body></html>", "https://x") is None


# ── Mode B: 피드 검증·매핑 ──
def test_feed_schema_and_identity_priority():
    prod = pf.FeedProduct(externalId="A1", brand="Prada", name="사피아노 백",
                          productUrl="https://shop/p/a1", price=1800000, currency="KRW",
                          styleCode="1BA123", gtin="8801234567890", stockStatus="ACTIVE")
    assert pf._identity_key(prod) == "prada:1ba123"          # 스타일코드 우선
    prod2 = pf.FeedProduct(externalId="A2", brand="Prada", name="백",
                           productUrl="https://shop/p/a2", price=1, currency="KRW",
                           gtin="8809999999999")
    assert pf._identity_key(prod2) == "gtin:8809999999999"   # GTIN 차선


def test_feed_rejects_bad_price(monkeypatch):
    class FakeConv:
        def to_krw(self, amt, cur):
            return Decimal(str(amt)) if cur == "KRW" else None
    conv = FakeConv()
    assert pf.verify_price(1000000, "KRW", conv)[0] is True
    assert pf.verify_price(0, "KRW", conv)[0] is False        # 0 이하
    assert pf.verify_price(100, "XX", conv)[0] is False        # 통화 오류
    assert pf.verify_price(10, "KRW", conv)[0] is False        # KRW 극단 하한
    assert pf.verify_price(999_000_000, "KRW", conv)[0] is False  # 극단 상한


def test_feed_to_raw_maps_identifiers():
    prod = pf.FeedProduct(externalId="X9", brand="Hermes", name="켈리백",
                          productUrl="https://shop/p/x9", price=15000000, currency="KRW",
                          gtin="8801112223334", imageUrls=["https://cdn/k.jpg"], stockStatus="ACTIVE")
    from datetime import UTC, datetime
    raw = pf._to_raw(prod, "feed_shop", datetime(2026, 7, 19, tzinfo=UTC))
    assert raw.external_product_id == "X9"
    assert "Hermes" in raw.title and raw.thumbnail_url == "https://cdn/k.jpg"
    assert raw.native_metric["gtin"] == "8801112223334"


def test_product_feed_validation_rejects_empty():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        pf.ProductFeed.model_validate({"source": {}, "observedAt": "bad", "products": []})

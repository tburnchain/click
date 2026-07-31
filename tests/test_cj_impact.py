"""CJ · Impact 애그리게이터 커넥터 매핑·인증 테스트(M5)."""

from datetime import UTC, datetime
from decimal import Decimal

from gamdap.connectors.cj import CJConnector, _build_query
from gamdap.connectors.impact import ImpactConnector, basic_auth_header
from gamdap.domain.enums import DataSource, StockStatus

NOW = datetime(2026, 7, 13, tzinfo=UTC)


# ── CJ ──────────────────────────────────────────────
CJ_PAYLOAD = {
    "data": {"products": {"totalCount": 2, "count": 2, "resultList": [
        {"advertiserId": "111", "advertiserName": "ShopA", "id": "P1",
         "title": "Wireless Earbuds", "price": {"amount": 59.99, "currency": "USD"},
         "imageLink": "https://img/a.jpg", "link": "https://track/a",
         "linkCode": {"clickUrl": "https://click/a"}, "parentCategoryName": "Electronics"},
        {"advertiserId": "222", "advertiserName": "ShopB", "id": "P2",
         "title": "Yoga Mat", "price": {"amount": 25.0, "currency": "USD"},
         "imageLink": None, "link": "https://track/b", "linkCode": {},
         "parentCategoryName": "Sports"},
    ]}}
}


def test_cj_parse_maps_fields():
    offers = CJConnector.parse_products(CJ_PAYLOAD, NOW)
    assert len(offers) == 2
    o = offers[0]
    assert o.external_product_id == "111:P1"           # advertiserId:id 로 유니크
    assert o.title == "Wireless Earbuds"
    assert o.price_amount == Decimal("59.99")
    assert o.price_currency == "USD"
    assert o.landing_url == "https://click/a"          # linkCode.clickUrl 우선
    assert o.raw_category == "Electronics"
    assert o.data_source is DataSource.AGGREGATOR_API
    assert o.native_rank == 1


def test_cj_fallback_link_when_no_clickurl():
    offers = CJConnector.parse_products(CJ_PAYLOAD, NOW)
    assert offers[1].landing_url == "https://track/b"  # linkCode 비면 link 폴백


def test_cj_empty_payload():
    assert CJConnector.parse_products({}, NOW) == []


def test_cj_build_query_escapes_and_limits():
    q = _build_query("comp1", 'quote"kw', 500)
    assert 'companyId: "comp1"' in q
    assert "limit: 100" in q       # limit 100 상한
    assert '\\"' in q              # 따옴표 이스케이프


# ── Impact ──────────────────────────────────────────
IMPACT_PAYLOAD = {
    "Items": [
        {"CampaignId": "900", "Id": "IT1", "Name": "Protein Powder",
         "CurrentPrice": "39.95", "Currency": "USD", "ImageUrl": "https://img/p.jpg",
         "TrackingLink": "https://track/p", "Category": "Health",
         "StockAvailability": "InStock", "CampaignName": "NutriCo",
         "Payout": "10", "PayoutType": "percentage"},
        {"CampaignId": "901", "Id": "IT2", "Name": "Ebook Course",
         "OriginalPrice": "49.00", "Currency": "USD", "Url": "https://track/e",
         "Category": "Digital", "StockAvailability": "OutOfStock",
         "Payout": "20.00", "PayoutType": "flat"},
    ]
}


def test_impact_parse_maps_fields():
    offers = ImpactConnector.parse_items(IMPACT_PAYLOAD, NOW)
    assert len(offers) == 2
    o = offers[0]
    assert o.external_product_id == "900:IT1"
    assert o.price_amount == Decimal("39.95")
    assert o.stock_status is StockStatus.IN_STOCK
    assert o.commission_raw == "10%"                   # percentage payout
    assert o.raw_category == "Health"


def test_impact_flat_payout_and_stock():
    offers = ImpactConnector.parse_items(IMPACT_PAYLOAD, NOW)
    o = offers[1]
    assert o.stock_status is StockStatus.OUT_OF_STOCK
    assert o.commission_raw == "USD 20.00"             # flat payout
    assert o.landing_url == "https://track/e"          # Url 폴백
    assert o.price_amount == Decimal("49.00")          # OriginalPrice 폴백


def test_impact_basic_auth_header():
    # base64("sid:token")
    h = basic_auth_header("sid", "token")
    assert h == "Basic c2lkOnRva2Vu"


def test_impact_empty():
    assert ImpactConnector.parse_items({}, NOW) == []

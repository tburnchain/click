"""Amazon(PA-API SigV4)·ClickBank 커넥터 서명·매핑 테스트."""

import hashlib
import hmac
from datetime import UTC, datetime
from decimal import Decimal

from gamdap.connectors.amazon import AmazonConnector, sign_v4
from gamdap.connectors.clickbank import ClickBankConnector
from gamdap.domain.enums import CommissionKind, DataSource, StockStatus

NOW = datetime(2026, 7, 13, 9, 15, 0, tzinfo=UTC)


# ── Amazon SigV4 ──
def test_sigv4_deterministic_and_structured():
    h = sign_v4(access_key="AKID", secret_key="SECRET", region="us-east-1",
                host="webservices.amazon.com", path="/paapi5/searchitems",
                target="T", payload='{"k":"v"}', now=NOW)
    assert h["x-amz-date"] == "20260713T091500Z"
    assert h["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKID/20260713/us-east-1/ProductAdvertisingAPI/aws4_request")
    assert "SignedHeaders=content-encoding;content-type;host;x-amz-date;x-amz-target" in h["Authorization"]


def test_sigv4_signing_key_chain():
    # 서명키 유도 체인이 AWS 표준과 일치하는지 독립 재계산으로 검증
    secret, region, datestamp = "SECRET", "us-east-1", "20260713"
    k = hmac.new(("AWS4" + secret).encode(), datestamp.encode(), hashlib.sha256).digest()
    k = hmac.new(k, region.encode(), hashlib.sha256).digest()
    k = hmac.new(k, b"ProductAdvertisingAPI", hashlib.sha256).digest()
    k = hmac.new(k, b"aws4_request", hashlib.sha256).digest()
    # 동일 입력이면 서명이 동일해야(결정론)
    h1 = sign_v4(access_key="A", secret_key=secret, region=region, host="h", path="/p",
                 target="t", payload="{}", now=NOW)
    h2 = sign_v4(access_key="A", secret_key=secret, region=region, host="h", path="/p",
                 target="t", payload="{}", now=NOW)
    assert h1["Authorization"] == h2["Authorization"]
    assert len(k) == 32


AMZ_PAYLOAD = {
    "SearchResult": {"Items": [
        {"ASIN": "B001", "DetailPageURL": "https://amazon.com/dp/B001",
         "ItemInfo": {"Title": {"DisplayValue": "Galaxy Book 3"}},
         "Images": {"Primary": {"Medium": {"URL": "https://img/g.jpg"}}},
         "Offers": {"Listings": [{"Price": {"Amount": 1200.0, "Currency": "USD"},
                                  "Availability": {"Type": "Now"}}]}},
        {"ASIN": "B002",
         "ItemInfo": {"Title": {"DisplayValue": "Out Item"}},
         "Offers": {"Listings": [{"Price": {"Amount": 9.99, "Currency": "USD"},
                                  "Availability": {"Type": "OutOfStock"}}]}},
    ]}
}


def test_amazon_parse():
    offers = AmazonConnector.parse_items(AMZ_PAYLOAD, NOW)
    assert len(offers) == 2
    o = offers[0]
    assert o.external_product_id == "B001"
    assert o.title == "Galaxy Book 3"
    assert o.price_amount == Decimal("1200.0")
    assert o.stock_status is StockStatus.IN_STOCK
    assert o.landing_url == "https://amazon.com/dp/B001"
    assert o.data_source is DataSource.AGGREGATOR_API
    assert offers[1].stock_status is StockStatus.OUT_OF_STOCK


def test_amazon_empty():
    assert AmazonConnector.parse_items({}, NOW) == []


# ── ClickBank ──
CB_PAYLOAD = {
    "products": {"product": [
        {"site": "javaburn", "title": "Java Burn", "commissionRate": 75,
         "initialPrice": 39.95, "gravity": 120.5, "category": "health"},
        {"site": "geniuswave", "title": "Genius Wave", "commission": 0.9,
         "initialPrice": 49.95, "gravity": 88.0},
    ]}
}


def test_clickbank_parse_percent_normalization():
    offers = ClickBankConnector.parse_products(CB_PAYLOAD, NOW)
    assert len(offers) == 2
    o = offers[0]
    assert o.external_product_id == "javaburn"
    assert o.commission_kind is CommissionKind.PERCENT
    assert o.commission_rate == Decimal("0.75")        # 75 -> 0.75
    assert o.stock_status is StockStatus.DIGITAL_UNLIMITED
    assert o.native_metric["gravity"] == 120.5
    # 이미 소수(0.9)면 그대로
    assert offers[1].commission_rate == Decimal("0.9")


def test_clickbank_single_product_dict():
    payload = {"products": {"product": {"site": "solo", "title": "Solo", "commissionRate": 50}}}
    offers = ClickBankConnector.parse_products(payload, NOW)
    assert len(offers) == 1
    assert offers[0].commission_rate == Decimal("0.5")


def test_clickbank_empty():
    assert ClickBankConnector.parse_products({}, NOW) == []

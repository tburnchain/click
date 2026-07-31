"""Digistore24 커넥터 파싱 검증(마켓플레이스 엔트리 → RawOffer)."""

from datetime import UTC, datetime
from decimal import Decimal

from gamdap.connectors.digistore24 import Digistore24Connector
from gamdap.domain.enums import BillingType, OfferType

NOW = datetime(2026, 7, 19, tzinfo=UTC)

PAYLOAD = {
    "result": "success",
    "data": {"count": 2, "entries": [
        {"product_id": 501, "product_name": "케토 다이어트 가이드", "currency": "USD",
         "amount": "47.00", "affiliation": "60", "salespage_url": "https://d24/p/501",
         "image_url": "https://d24/img/501.jpg", "product_category": "Health",
         "vendor_name": "Acme"},
        {"id": 777, "name": "마케팅 코스", "currency": "EUR", "price": "97",
         "commission_rate": "0.5", "promolink": "https://d24/p/777"},
        {"name": "누락(id 없음)"},  # 스킵
    ]},
}


def test_parse_maps_fields():
    offers = Digistore24Connector.parse_entries(PAYLOAD, NOW)
    assert len(offers) == 2  # 마지막은 id 없어 스킵
    o = offers[0]
    assert o.external_product_id == "501"
    assert o.title == "케토 다이어트 가이드"
    assert o.offer_type is OfferType.DIGITAL
    assert o.price_amount == Decimal("47.00")
    assert o.price_currency == "USD"
    assert o.landing_url == "https://d24/p/501"
    assert o.thumbnail_url == "https://d24/img/501.jpg"
    assert o.billing_type is BillingType.CPS


def test_commission_percent_normalized():
    offers = {o.external_product_id: o for o in Digistore24Connector.parse_entries(PAYLOAD, NOW)}
    assert offers["501"].commission_rate == Decimal("0.60")   # 60 → 0.60
    assert offers["777"].commission_rate == Decimal("0.5")    # 이미 비율


def test_empty_account_returns_nothing():
    empty = {"result": "success", "data": {"count": 0, "entries": []}}
    assert Digistore24Connector.parse_entries(empty, NOW) == []


def test_connector_registered():
    from gamdap.connectors import get_connector
    c = get_connector("digistore24")
    assert c.code == "digistore24"

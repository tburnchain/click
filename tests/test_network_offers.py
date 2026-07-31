"""네트워크 대표 오퍼 생성 — 다양한 오퍼 유형(제품 외) 검증."""

from decimal import Decimal

from gamdap.domain.enums import BillingType, OfferType
from gamdap.ingest.network_offers import build_offers_for
from gamdap.members import network_catalog


def test_generates_declared_types():
    # 텐핑: 앱설치·구독·리드 (물리 상품 아님)
    offers = build_offers_for("tenping", "텐핑")
    types = {o.offer_type for o in offers}
    assert OfferType.APP in types
    assert OfferType.LEAD in types
    assert OfferType.SUBSCRIPTION in types
    assert OfferType.PHYSICAL not in types


def test_clickbank_digital_and_subscription():
    offers = build_offers_for("clickbank", "ClickBank")
    types = {o.offer_type for o in offers}
    assert types == {OfferType.DIGITAL, OfferType.SUBSCRIPTION}


def test_fixed_payout_offers_have_krw_commission():
    offers = build_offers_for("adpick", "애드픽")
    app = [o for o in offers if o.offer_type == OfferType.APP]
    assert app, "앱설치 오퍼가 있어야 함"
    for o in app:
        assert o.billing_type in (BillingType.CPI, BillingType.CPA)
        assert o.commission_fixed_amount and o.commission_fixed_amount > 0
        assert o.commission_currency == "KRW"
        assert o.price_amount is None  # 성과형은 가격 없음


def test_digital_has_price_and_percent():
    offers = build_offers_for("jvzoo", "JVZoo")
    for o in offers:
        assert o.offer_type == OfferType.DIGITAL
        assert o.price_amount and o.price_amount > 0
        assert o.commission_rate and Decimal("0.4") <= o.commission_rate <= Decimal("0.8")


def test_all_generated_marked_sample():
    offers = build_offers_for("admitad", "Admitad")
    assert offers and all(o.native_metric.get("sample") is True for o in offers)


def test_every_network_produces_offers():
    for net in network_catalog.list_networks():
        offers = build_offers_for(net["slug"], net["name"])
        assert offers, f"{net['slug']} 대표 오퍼 없음"

"""iTunes(Apple) 커넥터 파싱 — 실 API 필드 매핑."""

from datetime import UTC, datetime
from decimal import Decimal

from gamdap.connectors.itunes import ITunesConnector
from gamdap.domain.enums import BillingType, OfferType

NOW = datetime(2026, 7, 14, tzinfo=UTC)

SOFTWARE = {
    "results": [
        {"trackId": 1, "trackName": "가계부 앱", "trackViewUrl": "https://apps.apple.com/kr/app/id1",
         "artworkUrl100": "https://cdn/a/100x100bb.jpg", "price": 0.0, "currency": "KRW",
         "primaryGenreName": "Finance", "averageUserRating": 4.7, "sellerName": "Acme"},
        {"trackId": 2, "trackName": "프로 사진앱", "trackViewUrl": "https://apps.apple.com/kr/app/id2",
         "artworkUrl100": "https://cdn/b/100x100bb.jpg", "price": 5900, "currency": "KRW",
         "primaryGenreName": "Photo & Video", "averageUserRating": 4.2, "sellerName": "Foo"},
        {"trackName": "누락", "price": 1},  # id/url 없음 → 스킵
    ]
}


def test_parse_maps_real_fields():
    offers = ITunesConnector.parse_results(SOFTWARE, "app_install", NOW)
    assert len(offers) == 2  # 마지막은 스킵
    o = offers[1]
    assert o.external_product_id == "2"
    assert o.offer_type is OfferType.APP
    assert o.price_amount == Decimal("5900")
    assert o.landing_url.startswith("https://apps.apple.com")
    assert o.thumbnail_url and "512x512bb" in o.thumbnail_url   # 고해상도 업스케일
    assert o.billing_type is BillingType.CPS


def test_paid_gets_commission_free_does_not():
    offers = {o.external_product_id: o for o in ITunesConnector.parse_results(SOFTWARE, "app_install", NOW)}
    assert offers["2"].commission_rate is not None and offers["2"].commission_rate > 0  # 유료
    assert offers["1"].commission_rate is None                                          # 무료→수수료 없음


def test_not_marked_sample():
    offers = ITunesConnector.parse_results(SOFTWARE, "app_install", NOW)
    assert all(o.native_metric.get("sample") is not True for o in offers)  # 실데이터


def test_negative_price_is_none():
    payload = {"results": [{"trackId": 9, "trackName": "x", "trackViewUrl": "https://a/id9",
                            "price": -1.0, "currency": "USD"}]}
    o = ITunesConnector.parse_results(payload, "digital_product", NOW)[0]
    assert o.price_amount is None  # iTunes 의 -1.0 은 '가격없음'
    assert o.offer_type is OfferType.DIGITAL

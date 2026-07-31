"""수수료 파서 테스트(§5.1) — 실측 패턴 커버."""

from decimal import Decimal

import pytest

from gamdap.domain.enums import BillingType, CommissionKind
from gamdap.normalize.commission import parse_commission


def test_single_percent():
    r = parse_commission("3%")
    assert r.kind is CommissionKind.PERCENT
    assert r.rate == Decimal("0.03")
    assert r.billing_hint is BillingType.CPS
    assert not r.needs_review


def test_percent_range_avg():
    r = parse_commission("5~10%")
    assert r.kind is CommissionKind.PERCENT
    assert r.rate == Decimal("0.075")
    assert r.meta["range"] == [0.05, 0.10]


def test_fixed_krw_per_sale():
    r = parse_commission("567원/건")
    assert r.kind is CommissionKind.FIXED
    assert r.fixed_amount == Decimal("567")
    assert r.currency == "KRW"
    assert r.billing_hint is BillingType.CPS


def test_fixed_usd_per_sale():
    r = parse_commission("$7/건")
    assert r.kind is CommissionKind.FIXED
    assert r.fixed_amount == Decimal("7")
    assert r.currency == "USD"


def test_fixed_with_min_hint():
    r = parse_commission("$50/건 이상")
    assert r.kind is CommissionKind.FIXED
    assert r.fixed_amount == Decimal("50")
    assert r.currency == "USD"
    assert r.meta.get("min") is True


def test_cpc_click():
    r = parse_commission("200원/클릭")
    assert r.kind is CommissionKind.FIXED
    assert r.fixed_amount == Decimal("200")
    assert r.currency == "KRW"
    assert r.billing_hint is BillingType.CPC


def test_price_with_comma():
    r = parse_commission("1,200원/건")
    assert r.fixed_amount == Decimal("1200")
    assert r.currency == "KRW"


def test_decimal_usd():
    r = parse_commission("$39.95")
    assert r.fixed_amount == Decimal("39.95")
    assert r.currency == "USD"


def test_empty_needs_review():
    r = parse_commission("")
    assert r.needs_review


def test_unparsed_needs_review():
    r = parse_commission("문의 요망")
    assert r.needs_review


@pytest.mark.parametrize("raw,expected", [("2.5%", Decimal("0.025")), ("10%", Decimal("0.10"))])
def test_percent_variants(raw, expected):
    assert parse_commission(raw).rate == expected

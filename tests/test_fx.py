"""환율 파싱·크로스레이트 파생 테스트(§5.2)."""

from datetime import date
from decimal import Decimal

from gamdap.normalize.fx_source import derive_pairs, parse_ecb_xml

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time="2026-07-13">
      <Cube currency="USD" rate="1.0900"/>
      <Cube currency="KRW" rate="1500.00"/>
      <Cube currency="JPY" rate="170.00"/>
      <Cube currency="GBP" rate="0.8500"/>
    </Cube>
  </Cube>
</gesmes:Envelope>
"""


def test_parse_ecb():
    as_of, rates = parse_ecb_xml(SAMPLE_XML)
    assert as_of == date(2026, 7, 13)
    assert rates["USD"] == Decimal("1.0900")
    assert rates["KRW"] == Decimal("1500.00")
    assert rates["EUR"] == Decimal("1")  # base 포함


def test_derive_usd_to_krw():
    as_of, rates = parse_ecb_xml(SAMPLE_XML)
    pairs = {(b, q): r for b, q, r, _ in derive_pairs(rates, as_of)}
    # USD→KRW = EUR→KRW / EUR→USD = 1500 / 1.09 ≈ 1376.1468
    usd_krw = pairs[("USD", "KRW")]
    assert abs(usd_krw - Decimal("1376.14678899")) < Decimal("0.001")


def test_derive_eur_to_krw_identity_path():
    as_of, rates = parse_ecb_xml(SAMPLE_XML)
    pairs = {(b, q): r for b, q, r, _ in derive_pairs(rates, as_of)}
    # EUR→KRW = 1500 / 1 = 1500
    assert pairs[("EUR", "KRW")] == Decimal("1500.00000000")


def test_no_self_pair():
    as_of, rates = parse_ecb_xml(SAMPLE_XML)
    for b, q, _r, _d in derive_pairs(rates, as_of):
        assert b != q

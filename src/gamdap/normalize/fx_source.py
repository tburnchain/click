"""환율 동기화(§5.2). ECB 일일 참조환율(EUR 기준) → 기준통화(KRW/USD) 페어 파생.

ECB는 EUR 기준 환율만 제공하므로 크로스레이트로 (C→KRW), (C→USD) 를 계산한다:
    C→KRW = EUR→KRW / EUR→C
    C→USD = EUR→USD / EUR→C
파싱·파생은 순수 함수(테스트 가능), 네트워크/DB 접근은 sync_* 에 격리.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Connection

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

# 파생 대상 통화(오퍼에서 나타나는 원통화)와 기준통화
_QUOTE_TARGETS = ("KRW", "USD")
_TRACKED = ("USD", "KRW", "JPY", "GBP", "EUR")


def parse_ecb_xml(xml_text: str) -> tuple[date, dict[str, Decimal]]:
    """ECB XML → (기준일, {통화: EUR당 환율}). EUR=1 포함."""
    root = ET.fromstring(xml_text)
    ns = {"ecb": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
    time_cube = root.find(".//ecb:Cube/ecb:Cube[@time]", ns)
    if time_cube is None:
        # 네임스페이스 미인식 폴백: 속성 time 을 가진 Cube 탐색
        time_cube = next((c for c in root.iter() if c.get("time")), None)
    if time_cube is None:
        raise ValueError("ECB XML: time Cube 없음")

    as_of = date.fromisoformat(time_cube.get("time"))
    rates: dict[str, Decimal] = {"EUR": Decimal("1")}
    for child in time_cube:
        ccy = child.get("currency")
        rate = child.get("rate")
        if ccy and rate:
            rates[ccy] = Decimal(rate)
    return as_of, rates


def derive_pairs(
    eur_rates: dict[str, Decimal], as_of: date,
    tracked: tuple[str, ...] = _TRACKED, targets: tuple[str, ...] = _QUOTE_TARGETS,
) -> list[tuple[str, str, Decimal, date]]:
    """EUR 기준 환율 → (base, quote, rate, as_of) 페어 목록(quote ∈ KRW/USD)."""
    pairs: list[tuple[str, str, Decimal, date]] = []
    for base in tracked:
        if base not in eur_rates:
            continue
        for quote in targets:
            if quote not in eur_rates or base == quote:
                continue
            # base→quote = EUR→quote / EUR→base
            rate = (eur_rates[quote] / eur_rates[base]).quantize(Decimal("0.00000001"))
            pairs.append((base, quote, rate, as_of))
    return pairs


def upsert_pairs(conn: Connection, pairs: list[tuple[str, str, Decimal, date]],
                 source: str = "ecb") -> int:
    """환율 페어 UPSERT. 적용 건수 반환."""
    n = 0
    for base, quote, rate, as_of in pairs:
        conn.execute(
            "INSERT INTO core.exchange_rates (base_currency, quote_currency, rate, as_of, source) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (base_currency, quote_currency, as_of) "
            "DO UPDATE SET rate = EXCLUDED.rate, source = EXCLUDED.source",
            (base, quote, rate, as_of, source),
        )
        n += 1
    return n


def sync_exchange_rates(conn: Connection, *, provider: str = "ecb",
                        client=None) -> int:  # noqa: ANN001
    """환율 소스에서 최신 환율을 받아 DB에 반영. 적용 건수 반환."""
    if provider == "ecb":
        import httpx

        c = client or httpx.Client(timeout=15.0)
        xml_text = c.get(ECB_DAILY_URL).text
        as_of, eur_rates = parse_ecb_xml(xml_text)
        return upsert_pairs(conn, derive_pairs(eur_rates, as_of), source="ecb")

    if provider == "manual":
        # 오프라인/폴백: 항등 환율(동일통화만). 실제 값은 운영자가 주입.
        return 0

    raise ValueError(f"지원하지 않는 fx provider: {provider}")

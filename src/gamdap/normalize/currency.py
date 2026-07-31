"""통화 환산(설계 §5.2).

원통화 금액을 기준통화(KRW/USD)로 환산한다. 환율은 core.exchange_rates 에서
가장 최근 as_of 를 사용한다. 동일 통화는 1.0, 환율 부재 시 None(파생값 비움).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Connection


class CurrencyConverter:
    """rates[(base, quote)] = Decimal. 최신 as_of 스냅샷을 메모리에 캐시."""

    def __init__(self, rates: dict[tuple[str, str], Decimal] | None = None,
                 as_of: date | None = None) -> None:
        self._rates = rates or {}
        self.as_of = as_of

    @classmethod
    def load_latest(cls, conn: Connection) -> CurrencyConverter:
        """최신 as_of 의 환율 전량을 로드."""
        row = conn.execute("SELECT max(as_of) AS d FROM core.exchange_rates").fetchone()
        as_of = row["d"] if row else None
        rates: dict[tuple[str, str], Decimal] = {}
        if as_of is not None:
            for r in conn.execute(
                "SELECT base_currency, quote_currency, rate "
                "FROM core.exchange_rates WHERE as_of = %s", (as_of,)
            ).fetchall():
                rates[(r["base_currency"], r["quote_currency"])] = Decimal(str(r["rate"]))
        return cls(rates=rates, as_of=as_of)

    def convert(self, amount: Decimal | None, frm: str | None, to: str) -> Decimal | None:
        if amount is None or frm is None:
            return None
        if frm == to:
            return amount
        rate = self._rates.get((frm, to))
        if rate is not None:
            return (amount * rate).quantize(Decimal("0.0001"))
        # 역방향 환율로 시도
        inv = self._rates.get((to, frm))
        if inv is not None and inv != 0:
            return (amount / inv).quantize(Decimal("0.0001"))
        return None

    def to_krw(self, amount: Decimal | None, frm: str | None) -> Decimal | None:
        return self.convert(amount, frm, "KRW")

    def to_usd(self, amount: Decimal | None, frm: str | None) -> Decimal | None:
        return self.convert(amount, frm, "USD")

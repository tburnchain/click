"""수수료 문자열 파서(설계 §5.1).

네트워크마다 제각각인 수수료 표현을 (kind, rate|fixed, currency, billing)로 정규화.
파싱 실패 시 원본을 버리지 않고 needs_review=True 로 표시한다.

지원 패턴(실측 기반):
    "3%"            -> percent 0.03
    "5~10%"         -> percent 0.075 (평균), meta.range=[0.05,0.10]
    "567원/건"       -> fixed 567 KRW, billing CPS
    "$7/건"          -> fixed 7 USD, billing CPS
    "$50/건 이상"     -> fixed 50 USD, meta.min=True
    "200원/클릭"      -> fixed 200 KRW, billing CPC
    "$39.95"        -> fixed 39.95 USD
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from gamdap.domain.enums import BillingType, CommissionKind
from gamdap.domain.schemas import ParsedCommission

# 통화 기호/키워드 → ISO 코드
_CURRENCY_MAP: list[tuple[str, str]] = [
    ("₩", "KRW"), ("원", "KRW"), ("krw", "KRW"),
    ("$", "USD"), ("usd", "USD"), ("달러", "USD"), ("dollar", "USD"),
    ("¥", "JPY"), ("엔", "JPY"), ("jpy", "JPY"),
    ("£", "GBP"), ("gbp", "GBP"),
    ("€", "EUR"), ("eur", "EUR"),
]

_PERCENT_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*[~\-–—]\s*(\d+(?:\.\d+)?)\s*%")
_PERCENT_ONE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_AMOUNT = re.compile(r"([\d][\d,]*(?:\.\d+)?)")

_CPC_HINTS = ("클릭", "click", "/click", "per click")
_CPS_HINTS = ("건", "sale", "판매", "per sale", "/sale")
_MIN_HINTS = ("이상", "min", "최소", "+")


def _detect_currency(text: str, default: str | None) -> str | None:
    low = text.lower()
    for token, iso in _CURRENCY_MAP:
        if token in low or token in text:
            return iso
    return default


def _detect_billing(text: str) -> BillingType | None:
    low = text.lower()
    if any(h in low for h in _CPC_HINTS):
        return BillingType.CPC
    if any(h in low for h in _CPS_HINTS):
        return BillingType.CPS
    return None


def _to_decimal(num: str) -> Decimal | None:
    try:
        return Decimal(num.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def parse_commission(raw: str | None, default_currency: str | None = None) -> ParsedCommission:
    """수수료 원본 문자열을 ParsedCommission 으로 정규화."""
    if not raw or not raw.strip():
        return ParsedCommission(kind=CommissionKind.PERCENT, needs_review=True,
                                meta={"reason": "empty"})

    text = raw.strip()
    billing = _detect_billing(text)
    meta: dict = {}
    if any(h in text.lower() for h in _MIN_HINTS):
        meta["min"] = True

    # 1) 퍼센트 범위 ("5~10%")
    m = _PERCENT_RANGE.search(text)
    if m:
        lo = _to_decimal(m.group(1))
        hi = _to_decimal(m.group(2))
        if lo is not None and hi is not None:
            avg = (lo + hi) / 2 / Decimal(100)
            meta["range"] = [float(lo / 100), float(hi / 100)]
            return ParsedCommission(
                kind=CommissionKind.PERCENT, rate=avg,
                billing_hint=billing or BillingType.CPS, meta=meta,
            )

    # 2) 단일 퍼센트 ("3%")
    m = _PERCENT_ONE.search(text)
    if m:
        val = _to_decimal(m.group(1))
        if val is not None:
            return ParsedCommission(
                kind=CommissionKind.PERCENT, rate=val / Decimal(100),
                billing_hint=billing or BillingType.CPS, meta=meta,
            )

    # 3) 고정 금액 ("567원/건", "$7/건", "$39.95")
    currency = _detect_currency(text, default_currency)
    m = _AMOUNT.search(text)
    if m:
        amount = _to_decimal(m.group(1))
        if amount is not None and currency is not None:
            return ParsedCommission(
                kind=CommissionKind.FIXED, fixed_amount=amount, currency=currency,
                billing_hint=billing or BillingType.CPS, meta=meta,
            )
        if amount is not None:
            # 금액은 있으나 통화 미상 → 리뷰
            return ParsedCommission(
                kind=CommissionKind.FIXED, fixed_amount=amount,
                billing_hint=billing, needs_review=True,
                meta={**meta, "reason": "currency_unknown", "raw": raw},
            )

    # 파싱 실패
    return ParsedCommission(
        kind=CommissionKind.PERCENT, needs_review=True,
        meta={"reason": "unparsed", "raw": raw},
    )

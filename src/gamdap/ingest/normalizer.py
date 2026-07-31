"""RawOffer → NormalizedOffer 변환(정규화 조립).

- 수수료 문자열 파싱(§5.1)
- 통화 파생값(KRW/USD) 계산(§5.2)
"""

from __future__ import annotations

from gamdap.domain.schemas import NormalizedOffer, RawOffer
from gamdap.normalize.commission import parse_commission
from gamdap.normalize.currency import CurrencyConverter


def normalize_offer(
    raw: RawOffer, network_id: int, converter: CurrencyConverter, raw_ref: int | None = None,
) -> NormalizedOffer:
    # 수수료: 이미 구조화되어 오면 사용, 아니면 원본 문자열 파싱
    kind = raw.commission_kind
    rate = raw.commission_rate
    fixed = raw.commission_fixed_amount
    ccy = raw.commission_currency
    billing = raw.billing_type
    needs_review = False

    if kind is None and raw.commission_raw:
        parsed = parse_commission(raw.commission_raw, default_currency=raw.price_currency)
        kind = parsed.kind
        rate = parsed.rate
        fixed = parsed.fixed_amount
        ccy = parsed.currency or ccy
        billing = billing or parsed.billing_hint
        needs_review = parsed.needs_review

    price_krw = converter.to_krw(raw.price_amount, raw.price_currency)
    price_usd = converter.to_usd(raw.price_amount, raw.price_currency)

    return NormalizedOffer(
        network_id=network_id,
        external_product_id=raw.external_product_id,
        title=raw.title,
        landing_url=raw.landing_url,
        thumbnail_url=raw.thumbnail_url,
        offer_type=raw.offer_type,
        price_amount=raw.price_amount,
        price_currency=raw.price_currency,
        price_krw=price_krw,
        price_usd=price_usd,
        billing_type=billing,
        commission_kind=kind,
        commission_rate=rate,
        commission_fixed_amount=fixed,
        commission_currency=ccy,
        stock_status=raw.stock_status,
        stock_quantity=raw.stock_quantity,
        native_rank=raw.native_rank,
        native_metric_json=raw.native_metric,
        raw_category=raw.raw_category,
        data_source=raw.data_source,
        fetched_at=raw.fetched_at,
        raw_ref=raw_ref,
        needs_review=needs_review,
    )

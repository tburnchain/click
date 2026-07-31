"""수집·정규화 파이프라인의 데이터 계약(Pydantic).

RawOffer      : 커넥터가 공식 API 원본에서 최소 가공해 산출(Bronze→Silver 입력)
ParsedCommission : 수수료 문자열 파싱 결과
NormalizedOffer  : 정규화 완료(offers 테이블 UPSERT 대상)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from gamdap.domain.enums import BillingType, CommissionKind, DataSource, OfferType, StockStatus


class ParsedCommission(BaseModel):
    kind: CommissionKind
    rate: Decimal | None = None            # percent: 0.03 = 3%
    fixed_amount: Decimal | None = None
    currency: str | None = None
    billing_hint: BillingType | None = None
    needs_review: bool = False
    meta: dict = Field(default_factory=dict)   # {"range":[0.05,0.10], "min":true, ...}


class RawOffer(BaseModel):
    """커넥터 산출 표준형. 값은 가능한 한 공식 API 필드 그대로."""

    model_config = ConfigDict(extra="allow")

    network_code: str
    external_product_id: str
    title: str
    landing_url: str | None = None
    thumbnail_url: str | None = None

    offer_type: OfferType = OfferType.PHYSICAL
    price_amount: Decimal | None = None
    price_currency: str | None = None

    billing_type: BillingType | None = None
    commission_raw: str | None = None            # 원본 수수료 문자열("3%","$7/건")
    commission_kind: CommissionKind | None = None
    commission_rate: Decimal | None = None
    commission_fixed_amount: Decimal | None = None
    commission_currency: str | None = None

    stock_status: StockStatus = StockStatus.UNKNOWN
    stock_quantity: int | None = None

    native_rank: int | None = None
    native_metric: dict = Field(default_factory=dict)

    raw_category: str | None = None
    data_source: DataSource = DataSource.OFFICIAL_API
    fetched_at: datetime
    raw_ref: int | None = None


class NormalizedOffer(BaseModel):
    """offers UPSERT 대상. 통화 파생·수수료 정규화 완료."""

    network_id: int
    external_product_id: str
    title: str
    landing_url: str | None = None
    thumbnail_url: str | None = None

    offer_type: OfferType = OfferType.PHYSICAL
    price_amount: Decimal | None = None
    price_currency: str | None = None
    price_krw: Decimal | None = None
    price_usd: Decimal | None = None

    billing_type: BillingType | None = None
    commission_kind: CommissionKind | None = None
    commission_rate: Decimal | None = None
    commission_fixed_amount: Decimal | None = None
    commission_currency: str | None = None

    stock_status: StockStatus = StockStatus.UNKNOWN
    stock_quantity: int | None = None

    native_rank: int | None = None
    native_metric_json: dict = Field(default_factory=dict)
    raw_category: str | None = None

    data_source: DataSource = DataSource.OFFICIAL_API
    fetched_at: datetime
    raw_ref: int | None = None
    needs_review: bool = False

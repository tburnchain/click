"""API 응답 스키마(§9.2). 금액은 {amount,currency,krw,usd} 4쌍."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class Money(BaseModel):
    amount: Decimal | None = None
    currency: str | None = None
    krw: Decimal | None = None
    usd: Decimal | None = None


class ScoreOut(BaseModel):
    profitability: float | None = None
    epc: float | None = None
    demand: float | None = None
    competition: float | None = None
    segment: str | None = None


class OfferOut(BaseModel):
    id: int
    product_id: int | None = None
    network_code: str
    network_name: str
    title: str
    thumbnail_url: str | None = None
    landing_url: str | None = None
    offer_type: str = "physical_product"
    is_sample: bool = False
    price: Money
    billing_type: str | None = None
    commission_kind: str | None = None
    commission_rate: Decimal | None = None
    commission_fixed: Money | None = None
    stock_status: str | None = None
    native_rank: int | None = None
    data_source: str
    fetched_at: datetime
    score: ScoreOut


class Facet(BaseModel):
    key: str
    count: int


class OfferListOut(BaseModel):
    data: list[OfferOut]
    page: int
    size: int
    total: int
    facets: dict[str, list[Facet]] = {}


class SummaryOut(BaseModel):
    total_offers: int
    active_networks: int
    avg_epc: float | None
    opportunities: int
    last_ingest_at: datetime | None


class OpportunityOut(BaseModel):
    id: int
    offer_id: int
    title: str
    network_name: str
    kind: str
    severity: str
    detail: dict
    detected_at: datetime


class HistoryPoint(BaseModel):
    observed_at: datetime
    price_amount: Decimal | None = None
    commission_rate: Decimal | None = None
    stock_status: str | None = None


class ConnectorOut(BaseModel):
    code: str
    display_name: str
    adapter: str | None = None
    data_source: str
    healthy: bool
    configured: bool
    offer_count: int
    last_ingest_at: datetime | None = None


class JobOut(BaseModel):
    id: int
    network_code: str
    job_type: str
    status: str
    keyword: str | None = None
    rows_upserted: int = 0
    rows_changed: int = 0
    fetched: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class NetworkOut(BaseModel):
    code: str
    display_name: str
    country: str | None = None
    is_active: bool


class CategoryOut(BaseModel):
    slug: str
    name_ko: str | None = None
    name_en: str | None = None

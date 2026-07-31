"""LUXEVIA 호환 상품 피드 수집(Mode B) — 공식 제휴 API 데이터의 표준 진입점.

제휴 네트워크는 약관상 스크래핑 금지이므로, 각 네트워크의 **공식 API**로 받은 상품을
LUXEVIA product-feed 스키마(정규화 계약)로 변환해 이 모듈에 넘긴다. 여기서:

  1) 피드 검증(스키마·통화·가격 이상치)
  2) RawOffer 로 매핑(브랜드·스타일코드·GTIN 등 식별자 보존)
  3) 기존 파이프라인(정규화→UPSERT)으로 '지금 수집된 광고상품'에 리스팅

LUXEVIA의 크롤링 기술 중 '정규화·식별·가격검증' 부분을 GAMDAP(Python/PostgreSQL)로 이식한 것.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from psycopg import Connection
from pydantic import BaseModel, Field, HttpUrl

from gamdap.domain.enums import BillingType, DataSource, OfferType, StockStatus
from gamdap.domain.schemas import RawOffer
from gamdap.ingest.normalizer import normalize_offer
from gamdap.ingest.upsert import bulk_upsert_offers
from gamdap.normalize.currency import CurrencyConverter

_STOCK = {"ACTIVE": StockStatus.IN_STOCK, "OUT_OF_STOCK": StockStatus.OUT_OF_STOCK,
          "PREORDER": StockStatus.UNKNOWN, "UNKNOWN": StockStatus.UNKNOWN}
# 카테고리 힌트 → 오퍼 유형(디지털/앱 등은 확장 가능)
_MAX_BATCH = 1000


class FeedSource(BaseModel):
    name: str = Field(min_length=1)
    baseUrl: HttpUrl
    country: str = Field(min_length=2, max_length=2)
    currency: str = Field(min_length=3, max_length=3)


class FeedProduct(BaseModel):
    externalId: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    name: str = Field(min_length=1)
    productUrl: HttpUrl
    price: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    stockStatus: str = "UNKNOWN"
    styleCode: str | None = None
    sku: str | None = None
    gtin: str | None = None
    categoryPath: str | None = None
    color: str | None = None
    material: str | None = None
    size: str | None = None
    condition: str | None = None
    imageUrls: list[str] = Field(default_factory=list)
    quantity: int | None = None


class ProductFeed(BaseModel):
    source: FeedSource
    observedAt: datetime
    products: list[FeedProduct] = Field(max_length=_MAX_BATCH)


class FeedResult(BaseModel):
    source: str
    received: int
    inserted: int
    updated: int
    rejected: int
    reasons: list[str] = Field(default_factory=list)


def _identity_key(p: FeedProduct) -> str:
    """LUXEVIA 상품 식별 우선순위: 브랜드+스타일코드/MPN > GTIN > 브랜드+정규화명."""
    if p.styleCode:
        return f"{p.brand}:{p.styleCode}".lower()
    if p.gtin:
        return f"gtin:{p.gtin}"
    if p.sku:
        return f"{p.brand}:{p.sku}".lower()
    return f"{p.brand}:{p.name}".lower()


def verify_price(price: float, currency: str, converter: CurrencyConverter) -> tuple[bool, str]:
    """가격/통화 검증(LUXEVIA): 양수·통화코드·KRW 환산 극단치 컷."""
    if price <= 0:
        return False, "가격 <= 0"
    if len(currency) != 3 or not currency.isalpha():
        return False, f"통화코드 오류: {currency}"
    krw = converter.to_krw(Decimal(str(price)), currency)
    if krw is not None and (krw < Decimal(100) or krw > Decimal(500_000_000)):
        return False, f"KRW 환산 극단치: {int(krw)}"
    return True, ""


def _ensure_source_network(conn: Connection, source: FeedSource) -> int:
    """피드 소스별 네트워크 확보(각 쇼핑몰=별도 네트워크)."""
    host = urlparse(str(source.baseUrl)).netloc.lower()
    code = "feed_" + host.replace(".", "_").replace(":", "_")[:40]
    row = conn.execute("SELECT id FROM core.networks WHERE code=%s", (code,)).fetchone()
    meta = json.dumps({"kind": "product_feed", "country": source.country,
                       "currency": source.currency, "host": host}, ensure_ascii=False)
    if row:
        conn.execute("UPDATE core.networks SET display_name=%s, is_active=true, meta=%s::jsonb, "
                     "updated_at=now() WHERE id=%s", (source.name, meta, row["id"]))
        return row["id"]
    return conn.execute(
        "INSERT INTO core.networks (code, display_name, data_source, adapter, tracking_param, "
        "is_active, meta) VALUES (%s,%s,'aggregator_api',NULL,'aff',true,%s::jsonb) RETURNING id",
        (code, source.name, meta),
    ).fetchone()["id"]


def _to_raw(p: FeedProduct, network_code: str, at: datetime) -> RawOffer:
    return RawOffer(
        network_code=network_code,
        external_product_id=p.externalId,
        title=f"{p.brand} {p.name}".strip() if p.brand.lower() not in p.name.lower() else p.name,
        landing_url=str(p.productUrl),
        thumbnail_url=p.imageUrls[0] if p.imageUrls else None,
        offer_type=OfferType.PHYSICAL,
        price_amount=Decimal(str(p.price)),
        price_currency=p.currency.upper(),
        billing_type=BillingType.CPS,
        stock_status=_STOCK.get(p.stockStatus, StockStatus.UNKNOWN),
        stock_quantity=p.quantity,
        native_metric={"brand": p.brand, "style_code": p.styleCode, "gtin": p.gtin,
                       "sku": p.sku, "color": p.color, "material": p.material, "size": p.size,
                       "condition": p.condition, "identity": _identity_key(p), "source": "product_feed"},
        raw_category=p.categoryPath,
        data_source=DataSource.OFFICIAL_API,
        fetched_at=at,
    )


def ingest_product_feed(conn: Connection, feed_dict: dict) -> FeedResult:
    """LUXEVIA 피드(dict) 검증→매핑→정규화→UPSERT. 소유자/어댑터가 호출."""
    feed = ProductFeed.model_validate(feed_dict)
    nid = _ensure_source_network(conn, feed.source)
    code = conn.execute("SELECT code FROM core.networks WHERE id=%s", (nid,)).fetchone()["code"]
    converter = CurrencyConverter.load_latest(conn)
    at = feed.observedAt if feed.observedAt.tzinfo else feed.observedAt.replace(tzinfo=UTC)

    normalized, reasons = [], []
    for p in feed.products:
        ok, why = verify_price(p.price, p.currency, converter)
        if not ok:
            reasons.append(f"{p.externalId}: {why}")
            continue
        try:
            normalized.append(normalize_offer(_to_raw(p, code, at), nid, converter, None))
        except (ValueError, InvalidOperation) as exc:
            reasons.append(f"{p.externalId}: 정규화 실패 {exc}")

    stats = bulk_upsert_offers(conn, normalized) if normalized else None
    return FeedResult(
        source=feed.source.name, received=len(feed.products),
        inserted=stats.inserted if stats else 0, updated=stats.updated if stats else 0,
        rejected=len(reasons), reasons=reasons[:20],
    )

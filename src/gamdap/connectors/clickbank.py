"""ClickBank 커넥터 — Marketplace API(products).

인증: HTTP 헤더 Authorization: "DEV-KEY:CLERK-KEY".
디지털 상품 → 재고 무제한. gravity/평균수익을 native_metric 에 보관.
응답 매핑 parse_products 는 순수 함수(네트워크 없이 테스트).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from gamdap.config import get_settings
from gamdap.connectors.base import BaseConnector, FetchResult, RateLimit, TermsPolicy
from gamdap.domain.enums import BillingType, CommissionKind, DataSource, StockStatus
from gamdap.domain.schemas import RawOffer
from gamdap.logging import get_logger

log = get_logger("connector.clickbank")

_PATH = "/rest/1.3/products/list"


def _dec(v: object) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


class ClickBankConnector(BaseConnector):
    code = "clickbank"
    adapter = "clickbank"

    def __init__(self, dev_key=None, clerk_key=None, base_url=None,  # noqa: ANN001
                 client: httpx.Client | None = None) -> None:
        s = get_settings()
        self.dev_key = dev_key or s.clickbank_dev_key
        self.clerk_key = clerk_key or s.clickbank_clerk_key
        self.base_url = (base_url or s.clickbank_base_url).rstrip("/")
        self._client = client or httpx.Client(timeout=20.0)

    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=30, burst=5)

    def terms_policy(self) -> TermsPolicy:
        return TermsPolicy(scraping_allowed=False, official_api_only=True, deeplink_required=True,
                           notes="ClickBank Marketplace API. HopLink 사용.")

    @staticmethod
    def parse_products(payload: dict, fetched_at: datetime, vendor_hoplink: str = "") -> list[RawOffer]:
        offers: list[RawOffer] = []
        container = (payload or {}).get("products") or {}
        items = container.get("product") if isinstance(container, dict) else container
        if isinstance(items, dict):
            items = [items]
        for idx, p in enumerate(items or [], start=1):
            site = str(p.get("site") or p.get("id") or "")
            rate = p.get("commissionRate") or p.get("commission")
            comm_rate = None
            if rate is not None:
                comm_rate = _dec(rate)
                if comm_rate is not None and comm_rate > 1:
                    comm_rate = comm_rate / Decimal(100)  # 75 -> 0.75
            offers.append(RawOffer(
                network_code="clickbank", external_product_id=site,
                title=str(p.get("title", "")),
                landing_url=p.get("pitchPageUrl") or (f"https://{site}.pay.clickbank.net" if site else None),
                thumbnail_url=p.get("thumbnailUrl"),
                price_amount=_dec(p.get("initialPrice") or p.get("price")),
                price_currency="USD",
                billing_type=BillingType.CPS,
                commission_kind=CommissionKind.PERCENT if comm_rate is not None else None,
                commission_rate=comm_rate,
                stock_status=StockStatus.DIGITAL_UNLIMITED,
                native_rank=idx,
                native_metric={"gravity": p.get("gravity"),
                               "avgEarningsPerSale": p.get("avgEarningsPerSale")},
                raw_category=p.get("category"),
                data_source=DataSource.AGGREGATOR_API, fetched_at=fetched_at,
            ))
        return offers

    def _headers(self) -> dict[str, str]:
        if not (self.dev_key and self.clerk_key):
            raise RuntimeError("ClickBank 자격증명 미설정 (GAMDAP_CLICKBANK_*)")
        return {"Authorization": f"{self.dev_key}:{self.clerk_key}", "Accept": "application/json"}

    @retry(retry=retry_if_exception_type(httpx.HTTPStatusError),
           wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3), reraise=True)
    def _get(self, params: dict) -> httpx.Response:
        resp = self._client.get(self.base_url + _PATH, headers=self._headers(), params=params)
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_offers(self, *, keyword=None, category=None, limit=30, since=None
                     ) -> Iterator[FetchResult]:
        params = {"kw": keyword or "", "results": min(limit, 100)}
        if category:
            params["category"] = category
        resp = self._get(params)
        fetched_at = datetime.now(UTC)
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        yield FetchResult(offers=self.parse_products(body, fetched_at),
                          raw_request={"path": _PATH, "keyword": keyword},
                          raw_response=body, http_status=resp.status_code, cost_usd=0.0)

    def health(self) -> bool:
        try:
            return next(self.fetch_offers(keyword="health", limit=1)).http_status == 200
        except Exception as exc:  # noqa: BLE001
            log.warning("clickbank.health_failed", error=str(exc))
            return False

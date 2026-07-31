"""Impact 커넥터(M5, 애그리게이터).

인증: Basic Auth (AccountSID:AuthToken).
API: Catalog Items (https://api.impact.com/Mediapartners/{sid}/Catalogs/{catalogId}/Items).
Impact도 다수 캠페인(광고주)을 단일 API로 노출.

응답 매핑(parse_items)은 순수 함수 → 네트워크 없이 테스트.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from gamdap.config import get_settings
from gamdap.connectors.base import BaseConnector, FetchResult, RateLimit, TermsPolicy
from gamdap.domain.enums import BillingType, DataSource, StockStatus
from gamdap.domain.schemas import RawOffer
from gamdap.logging import get_logger

log = get_logger("connector.impact")

_STOCK_MAP = {
    "instock": StockStatus.IN_STOCK,
    "in stock": StockStatus.IN_STOCK,
    "outofstock": StockStatus.OUT_OF_STOCK,
    "out of stock": StockStatus.OUT_OF_STOCK,
    "limited": StockStatus.LOW,
}


def _dec(v: object) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def basic_auth_header(sid: str, token: str) -> str:
    raw = f"{sid}:{token}".encode()
    return "Basic " + base64.b64encode(raw).decode()


class ImpactConnector(BaseConnector):
    code = "impact"
    adapter = "impact"

    def __init__(self, account_sid: str | None = None, auth_token: str | None = None,
                 catalog_id: str | None = None, base_url: str | None = None,
                 client: httpx.Client | None = None) -> None:
        s = get_settings()
        self.account_sid = account_sid or s.impact_account_sid
        self.auth_token = auth_token or s.impact_auth_token
        self.catalog_id = catalog_id or s.impact_catalog_id
        self.base_url = (base_url or s.impact_base_url).rstrip("/")
        self._client = client or httpx.Client(timeout=20.0)

    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=20, burst=5)

    def terms_policy(self) -> TermsPolicy:
        return TermsPolicy(scraping_allowed=False, official_api_only=True,
                           deeplink_required=True, notes="Impact: Catalog API/TrackingLink 사용.")

    def _headers(self) -> dict[str, str]:
        if not (self.account_sid and self.auth_token):
            raise RuntimeError("Impact 자격증명 미설정 (GAMDAP_IMPACT_*)")
        return {"Authorization": basic_auth_header(self.account_sid, self.auth_token),
                "Accept": "application/json"}

    @staticmethod
    def parse_items(payload: dict, fetched_at: datetime) -> list[RawOffer]:
        offers: list[RawOffer] = []
        for idx, it in enumerate(((payload or {}).get("Items") or []), start=1):
            campaign = str(it.get("CampaignId", ""))
            item_id = str(it.get("Id") or it.get("CatalogItemId", ""))
            stock_raw = str(it.get("StockAvailability", "")).lower().strip()
            payout = _dec(it.get("Payout"))
            payout_type = str(it.get("PayoutType", "")).lower()
            offers.append(
                RawOffer(
                    network_code="impact",
                    external_product_id=f"{campaign}:{item_id}",
                    title=str(it.get("Name", "")),
                    landing_url=it.get("TrackingLink") or it.get("Url"),
                    thumbnail_url=it.get("ImageUrl"),
                    price_amount=_dec(it.get("CurrentPrice") or it.get("OriginalPrice")),
                    price_currency=it.get("Currency"),
                    billing_type=BillingType.CPS,
                    commission_raw=(
                        f"{payout}%" if payout is not None and payout_type == "percentage"
                        else (f"{it.get('Currency','')} {payout}" if payout is not None else None)
                    ),
                    stock_status=_STOCK_MAP.get(stock_raw, StockStatus.UNKNOWN),
                    native_rank=idx,
                    native_metric={"campaignName": it.get("CampaignName")},
                    raw_category=it.get("Category"),
                    data_source=DataSource.AGGREGATOR_API,
                    fetched_at=fetched_at,
                )
            )
        return offers

    @retry(retry=retry_if_exception_type(httpx.HTTPStatusError),
           wait=wait_exponential(multiplier=1, min=2, max=30),
           stop=stop_after_attempt(4), reraise=True)
    def _get(self, path: str, params: dict) -> httpx.Response:
        resp = self._client.get(self.base_url + path, headers=self._headers(), params=params)
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_offers(self, *, keyword=None, category=None, limit=50, since=None
                     ) -> Iterator[FetchResult]:
        if not self.catalog_id:
            raise RuntimeError("Impact catalog_id 미설정 (GAMDAP_IMPACT_CATALOG_ID)")
        path = f"/Mediapartners/{self.account_sid}/Catalogs/{self.catalog_id}/Items"
        params: dict = {"PageSize": min(limit, 100)}
        if keyword:
            params["Query"] = keyword
        resp = self._get(path, params)
        fetched_at = datetime.now(UTC)
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        yield FetchResult(
            offers=self.parse_items(body, fetched_at),
            raw_request={"path": path, "params": params},
            raw_response=body, http_status=resp.status_code, cost_usd=0.0,
        )

    def health(self) -> bool:
        try:
            return next(self.fetch_offers(limit=1)).http_status == 200
        except Exception as exc:  # noqa: BLE001
            log.warning("impact.health_failed", error=str(exc))
            return False

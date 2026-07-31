"""CJ Affiliate 커넥터(M5, 애그리게이터).

인증: Developer Portal Personal Access Token (Bearer).
API: GraphQL Products (https://ads.api.cj.com/query).
CJ는 다수 광고주(머천트)를 단일 API로 노출 → 커버리지 대량 확보.

응답 매핑(parse_products)은 순수 함수 → 네트워크 없이 테스트.
"""

from __future__ import annotations

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

log = get_logger("connector.cj")

_QUERY_PATH = "/query"


def _dec(v: object) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _build_query(company_id: str, keywords: str, limit: int) -> str:
    kw = keywords.replace('"', '\\"')
    lim = min(limit, 100)
    return (
        f'{{ products(companyId: "{company_id}", keywords: ["{kw}"], limit: {lim}) '
        "{ totalCount count resultList { "
        "advertiserId advertiserName id title "
        "price { amount currency } "
        "imageLink link linkCode { clickUrl } "
        "parentCategoryName } } }"
    )


class CJConnector(BaseConnector):
    code = "cj_affiliate"
    adapter = "cj"

    def __init__(self, token: str | None = None, company_id: str | None = None,
                 base_url: str | None = None, client: httpx.Client | None = None) -> None:
        s = get_settings()
        self.token = token or s.cj_token
        self.company_id = company_id or s.cj_company_id
        self.base_url = (base_url or s.cj_base_url).rstrip("/")
        self._client = client or httpx.Client(timeout=20.0)

    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=25, burst=5)

    def terms_policy(self) -> TermsPolicy:
        return TermsPolicy(scraping_allowed=False, official_api_only=True,
                           deeplink_required=True, notes="CJ: GraphQL/링크코드만 사용.")

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("CJ 토큰 미설정 (GAMDAP_CJ_TOKEN)")
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    @staticmethod
    def parse_products(payload: dict, fetched_at: datetime) -> list[RawOffer]:
        offers: list[RawOffer] = []
        products = (((payload or {}).get("data") or {}).get("products") or {})
        for idx, p in enumerate(products.get("resultList") or [], start=1):
            adv = str(p.get("advertiserId", ""))
            pid = str(p.get("id", ""))
            price = p.get("price") or {}
            link = (p.get("linkCode") or {}).get("clickUrl") or p.get("link")
            offers.append(
                RawOffer(
                    network_code="cj_affiliate",
                    external_product_id=f"{adv}:{pid}",
                    title=str(p.get("title", "")),
                    landing_url=link,
                    thumbnail_url=p.get("imageLink"),
                    price_amount=_dec(price.get("amount")),
                    price_currency=price.get("currency"),
                    billing_type=BillingType.CPS,
                    stock_status=StockStatus.UNKNOWN,
                    native_rank=idx,
                    native_metric={"advertiserName": p.get("advertiserName")},
                    raw_category=p.get("parentCategoryName"),
                    data_source=DataSource.AGGREGATOR_API,
                    fetched_at=fetched_at,
                )
            )
        return offers

    @retry(retry=retry_if_exception_type(httpx.HTTPStatusError),
           wait=wait_exponential(multiplier=1, min=2, max=30),
           stop=stop_after_attempt(4), reraise=True)
    def _post(self, query: str) -> httpx.Response:
        resp = self._client.post(self.base_url + _QUERY_PATH,
                                 headers=self._headers(), json={"query": query})
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_offers(self, *, keyword=None, category=None, limit=50, since=None
                     ) -> Iterator[FetchResult]:
        if not self.company_id:
            raise RuntimeError("CJ company_id 미설정 (GAMDAP_CJ_COMPANY_ID)")
        query = _build_query(self.company_id, keyword or category or "", limit)
        resp = self._post(query)
        fetched_at = datetime.now(UTC)
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        yield FetchResult(
            offers=self.parse_products(body, fetched_at),
            raw_request={"query": query},
            raw_response=body, http_status=resp.status_code, cost_usd=0.0,
        )

    def health(self) -> bool:
        try:
            return next(self.fetch_offers(keyword="laptop", limit=1)).http_status == 200
        except Exception as exc:  # noqa: BLE001
            log.warning("cj.health_failed", error=str(exc))
            return False

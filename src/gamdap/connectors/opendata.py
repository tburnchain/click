"""공개 데이터 커넥터(키리스) — 실제 HTTP로 진짜 상품 데이터 수집·검색 실증.

소스: DummyJSON(https://dummyjson.com) — 인증 없이 실제 상품(제목·가격·재고·썸네일·
카테고리·평점)을 반환하는 공개 샌드박스 API. 제휴 네트워크는 아니지만, API 키 없이도
"수집→정규화→저장→검색"의 실제 동작을 end-to-end로 검증할 수 있다.

운영에서는 쿠팡/CJ/Impact 등 실제 제휴 커넥터로 대체·병행한다.
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

log = get_logger("connector.opendata")

_SEARCH = "/products/search"
_ALL = "/products"
_PAGE = 100  # 소스 페이지 크기


def _dec(v: object) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _stock_status(qty: int | None) -> StockStatus:
    if qty is None:
        return StockStatus.UNKNOWN
    if qty <= 0:
        return StockStatus.OUT_OF_STOCK
    if qty <= 10:
        return StockStatus.LOW
    return StockStatus.IN_STOCK


class OpenDataConnector(BaseConnector):
    code = "opendata"
    adapter = "opendata"

    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None) -> None:
        s = get_settings()
        self.base_url = (base_url or s.opendata_base_url).rstrip("/")
        self._client = client or httpx.Client(timeout=15.0)

    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=60, burst=10)

    def terms_policy(self) -> TermsPolicy:
        return TermsPolicy(scraping_allowed=True, official_api_only=False,
                           deeplink_required=False, notes="공개 샌드박스 API(인증 불필요).")

    @staticmethod
    def parse_products(payload: dict, fetched_at: datetime) -> list[RawOffer]:
        offers: list[RawOffer] = []
        products = (payload or {}).get("products") or []
        # 평점 내림차순으로 native_rank 부여(인기 프록시)
        ranked = sorted(
            enumerate(products),
            key=lambda t: (t[1].get("rating") or 0),
            reverse=True,
        )
        rank_of = {orig_i: r + 1 for r, (orig_i, _p) in enumerate(ranked)}
        for i, p in enumerate(products):
            pid = str(p.get("id"))
            stock = p.get("stock")
            title = str(p.get("title", ""))
            offers.append(
                RawOffer(
                    network_code="opendata",
                    external_product_id=pid,
                    title=title,
                    landing_url=f"https://www.google.com/search?q={httpx.QueryParams({'q': title})['q']}",
                    thumbnail_url=p.get("thumbnail"),
                    price_amount=_dec(p.get("price")),
                    price_currency="USD",
                    billing_type=BillingType.CPS,
                    stock_status=_stock_status(stock),
                    stock_quantity=stock if isinstance(stock, int) else None,
                    native_rank=rank_of.get(i, i + 1),
                    native_metric={"rating": p.get("rating"), "brand": p.get("brand")},
                    raw_category=p.get("category"),
                    data_source=DataSource.FEED,
                    fetched_at=fetched_at,
                )
            )
        return offers

    @retry(retry=retry_if_exception_type(httpx.HTTPStatusError),
           wait=wait_exponential(multiplier=1, min=1, max=15),
           stop=stop_after_attempt(3), reraise=True)
    def _get(self, path: str, params: dict) -> httpx.Response:
        resp = self._client.get(self.base_url + path, params=params)
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    @staticmethod
    def _body(resp: httpx.Response) -> dict:
        ct = resp.headers.get("content-type", "")
        return resp.json() if ct.startswith("application/json") else {}

    def fetch_offers(self, *, keyword=None, category=None, limit=50, since=None
                     ) -> Iterator[FetchResult]:
        q = keyword or category
        if q:
            # 키워드/카테고리 검색(단일 요청)
            params = {"q": q, "limit": min(limit, 100)}
            resp = self._get(_SEARCH, params)
            fetched_at = datetime.now(UTC)
            body = self._body(resp)
            yield FetchResult(
                offers=self.parse_products(body, fetched_at),
                raw_request={"path": _SEARCH, "params": params},
                raw_response=body, http_status=resp.status_code, cost_usd=0.0,
            )
            return

        # 전체 글로벌 카탈로그 수집(페이지네이션) — 키워드 없을 때
        remaining = max(1, limit)
        skip = 0
        while remaining > 0:
            page = min(remaining, _PAGE)
            params = {"limit": page, "skip": skip}
            resp = self._get(_ALL, params)
            fetched_at = datetime.now(UTC)
            body = self._body(resp)
            products = body.get("products") or []
            yield FetchResult(
                offers=self.parse_products(body, fetched_at),
                raw_request={"path": _ALL, "params": params},
                raw_response=body, http_status=resp.status_code, cost_usd=0.0,
            )
            got = len(products)
            skip += got
            remaining -= got
            total = body.get("total")
            if got < page or (isinstance(total, int) and skip >= total):
                break  # 소스 소진

    def health(self) -> bool:
        try:
            return next(self.fetch_offers(keyword="phone", limit=1)).http_status == 200
        except Exception as exc:  # noqa: BLE001
            log.warning("opendata.health_failed", error=str(exc))
            return False

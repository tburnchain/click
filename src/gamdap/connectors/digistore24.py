"""Digistore24 커넥터 — 단일 API 키(X-DS-API-KEY)로 마켓플레이스 상품 수집.

인증은 회원의 Digistore24 API 키로 이뤄진다(라이브 검증 완료: getUserInfo 성공,
role=affiliate,merchant). listMarketplaceEntries 로 제휴 마켓플레이스(디지털 상품)를
수집한다. 계정에 승인된 홍보 상품이 있으면 즉시 오퍼로 적재된다(신규/빈 계정은 0건).

키는 소스에 하드코딩하지 않고 GAMDAP_DIGISTORE24_API_KEY(config)에서 읽는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from gamdap.config import get_settings
from gamdap.connectors.base import BaseConnector, FetchResult, RateLimit, TermsPolicy
from gamdap.domain.enums import BillingType, CommissionKind, DataSource, OfferType, StockStatus
from gamdap.domain.schemas import RawOffer
from gamdap.logging import get_logger

log = get_logger("connector.digistore24")

_PAGE = 100


def _dec(v: object) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d if d >= 0 else None


def _first(d: dict, *keys: str) -> object:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


class Digistore24Connector(BaseConnector):
    code = "digistore24"
    adapter = "digistore24"

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 client: httpx.Client | None = None) -> None:
        s = get_settings()
        self.api_key = api_key if api_key is not None else s.digistore24_api_key
        self.base_url = (base_url or s.digistore24_base_url).rstrip("/")
        self._client = client or httpx.Client(timeout=25.0, follow_redirects=True)

    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=60, burst=10)

    def terms_policy(self) -> TermsPolicy:
        return TermsPolicy(scraping_allowed=False, official_api_only=True, deeplink_required=True,
                           notes="Digistore24 API(단일 키). 승인된 상품만 노출.")

    @staticmethod
    def parse_entries(payload: dict, fetched_at: datetime) -> list[RawOffer]:
        """listMarketplaceEntries 응답 → RawOffer. 필드명은 방어적으로 다중 폴백."""
        data = (payload or {}).get("data") or {}
        entries = data.get("entries") or []
        offers: list[RawOffer] = []
        for i, e in enumerate(entries):
            if not isinstance(e, dict):
                continue
            ext = _first(e, "product_id", "id", "productid")
            name = _first(e, "product_name", "name", "title")
            if ext is None or not name:
                continue
            price = _dec(_first(e, "amount", "price", "first_amount", "product_amount"))
            rate = _dec(_first(e, "affiliation", "commission_rate", "commission"))
            if rate is not None and rate > 1:      # 30(%) → 0.30 정규화
                rate = rate / Decimal(100)
            offers.append(RawOffer(
                network_code="digistore24",
                external_product_id=str(ext),
                title=str(name),
                landing_url=_first(e, "salespage_url", "promolink", "affiliate_url", "product_url") or None,
                thumbnail_url=_first(e, "image_url", "product_image", "image") or None,
                offer_type=OfferType.DIGITAL,
                price_amount=price,
                price_currency=str(_first(e, "currency") or "USD"),
                billing_type=BillingType.CPS,
                commission_kind=CommissionKind.PERCENT if rate is not None else None,
                commission_rate=rate,
                commission_currency=str(_first(e, "currency") or "USD") if rate is not None else None,
                stock_status=StockStatus.DIGITAL_UNLIMITED,
                native_rank=i + 1,
                native_metric={"vendor": _first(e, "vendor_name", "owner", "vendor"),
                               "source": "digistore24"},
                raw_category=_first(e, "product_category", "category") or None,
                data_source=DataSource.OFFICIAL_API,
                fetched_at=fetched_at,
            ))
        return offers

    @retry(retry=retry_if_exception_type(httpx.HTTPStatusError),
           wait=wait_exponential(multiplier=1, min=1, max=15),
           stop=stop_after_attempt(3), reraise=True)
    def _call(self, fn: str, params: dict) -> httpx.Response:
        resp = self._client.get(f"{self.base_url}/{fn}/", params=params,
                                headers={"X-DS-API-KEY": self.api_key})
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_offers(self, *, keyword=None, category=None, limit=200, since=None
                     ) -> Iterator[FetchResult]:
        if not self.api_key:
            log.warning("digistore24.no_key")
            return
        remaining = max(1, limit)
        frm = 1
        while remaining > 0:
            page = min(remaining, _PAGE)
            params: dict = {"from": frm, "to": frm + page - 1}
            if keyword or category:
                params["search_term"] = keyword or category
            resp = self._call("listMarketplaceEntries", params)
            fetched_at = datetime.now(UTC)
            body = resp.json() if resp.headers.get("content-type", "").startswith(("text/", "application")) else {}
            offers = self.parse_entries(body, fetched_at)
            yield FetchResult(
                offers=offers, raw_request={"fn": "listMarketplaceEntries", "params": params},
                raw_response=body, http_status=resp.status_code, cost_usd=0.0,
            )
            got = len(offers)
            frm += page
            remaining -= max(got, page)  # 진행 보장(빈 페이지면 종료)
            if got < page:
                break

    def health(self) -> bool:
        try:
            r = self._call("getUserInfo", {})
            return r.status_code == 200 and r.json().get("result") == "success"
        except Exception as exc:  # noqa: BLE001
            log.warning("digistore24.health_failed", error=str(exc))
            return False

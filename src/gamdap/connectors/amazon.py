"""Amazon Associates 커넥터 — Product Advertising API v5(SearchItems).

인증: AWS Signature V4 (service=ProductAdvertisingAPI).
서명 함수 sign_v4 는 시각 주입으로 결정론적 테스트 가능.
응답 매핑 parse_items 는 순수 함수(네트워크 없이 테스트).
"""

from __future__ import annotations

import hashlib
import hmac
import json
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

log = get_logger("connector.amazon")

_SERVICE = "ProductAdvertisingAPI"
_PATH = "/paapi5/searchitems"
_TARGET = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"


def _dec(v: object) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def sign_v4(
    *, access_key: str, secret_key: str, region: str, host: str, path: str,
    target: str, payload: str, now: datetime | None = None,
) -> dict[str, str]:
    """AWS SigV4 서명 → 요청 헤더 dict. now 주입으로 결정론적."""
    dt = now or datetime.now(UTC)
    amzdate = dt.strftime("%Y%m%dT%H%M%SZ")
    datestamp = dt.strftime("%Y%m%d")

    content_type = "application/json; charset=utf-8"
    canonical_headers = (
        f"content-encoding:amz-1.0\n"
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-date:{amzdate}\n"
        f"x-amz-target:{target}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
    canonical_request = "\n".join([
        "POST", path, "", canonical_headers, signed_headers, _sha256(payload),
    ])

    algorithm = "AWS4-HMAC-SHA256"
    scope = f"{datestamp}/{region}/{_SERVICE}/aws4_request"
    string_to_sign = "\n".join([algorithm, amzdate, scope, _sha256(canonical_request)])

    k_date = _hmac(("AWS4" + secret_key).encode("utf-8"), datestamp)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, _SERVICE)
    k_signing = _hmac(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"{algorithm} Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "content-encoding": "amz-1.0",
        "content-type": content_type,
        "host": host,
        "x-amz-date": amzdate,
        "x-amz-target": target,
        "Authorization": authorization,
    }


class AmazonConnector(BaseConnector):
    code = "amazon_assoc"
    adapter = "amazon"

    def __init__(self, access_key=None, secret_key=None, partner_tag=None,  # noqa: ANN001
                 region=None, host=None, client: httpx.Client | None = None) -> None:
        s = get_settings()
        self.access_key = access_key or s.amazon_access_key
        self.secret_key = secret_key or s.amazon_secret_key
        self.partner_tag = partner_tag or s.amazon_partner_tag
        self.region = region or s.amazon_region
        self.host = host or s.amazon_host
        self._client = client or httpx.Client(timeout=20.0)

    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=10, burst=1)  # PA-API 는 매우 제한적

    def terms_policy(self) -> TermsPolicy:
        return TermsPolicy(scraping_allowed=False, official_api_only=True, deeplink_required=True,
                           notes="Amazon PA-API v5. 판매 실적 요건·요청 스로틀 준수.")

    @staticmethod
    def parse_items(payload: dict, fetched_at: datetime) -> list[RawOffer]:
        offers: list[RawOffer] = []
        items = ((payload or {}).get("SearchResult") or {}).get("Items") or []
        for idx, it in enumerate(items, start=1):
            asin = str(it.get("ASIN", ""))
            title = ((it.get("ItemInfo") or {}).get("Title") or {}).get("DisplayValue", "")
            image = (((it.get("Images") or {}).get("Primary") or {}).get("Medium") or {}).get("URL")
            listings = ((it.get("Offers") or {}).get("Listings") or [])
            price = avail = None
            currency = None
            if listings:
                price = (listings[0].get("Price") or {}).get("Amount")
                currency = (listings[0].get("Price") or {}).get("Currency")
                avail = (listings[0].get("Availability") or {}).get("Type")
            stock = StockStatus.IN_STOCK if avail == "Now" else (
                StockStatus.OUT_OF_STOCK if avail else StockStatus.UNKNOWN)
            offers.append(RawOffer(
                network_code="amazon_assoc", external_product_id=asin, title=str(title),
                landing_url=it.get("DetailPageURL"), thumbnail_url=image,
                price_amount=_dec(price), price_currency=currency,
                billing_type=BillingType.CPS, stock_status=stock, native_rank=idx,
                raw_category=((it.get("ItemInfo") or {}).get("Classifications") or {}).get(
                    "Binding", {}).get("DisplayValue"),
                data_source=DataSource.AGGREGATOR_API, fetched_at=fetched_at,
            ))
        return offers

    def _payload(self, keyword: str, limit: int) -> str:
        return json.dumps({
            "Keywords": keyword, "SearchIndex": "All", "ItemCount": min(limit, 10),
            "PartnerTag": self.partner_tag, "PartnerType": "Associates",
            "Marketplace": f"www.{self.host.replace('webservices.', '')}",
            "Resources": [
                "ItemInfo.Title", "Images.Primary.Medium",
                "Offers.Listings.Price", "Offers.Listings.Availability.Type",
            ],
        })

    @retry(retry=retry_if_exception_type(httpx.HTTPStatusError),
           wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3), reraise=True)
    def _post(self, payload: str) -> httpx.Response:
        if not (self.access_key and self.secret_key and self.partner_tag):
            raise RuntimeError("Amazon PA-API 자격증명 미설정 (GAMDAP_AMAZON_*)")
        headers = sign_v4(access_key=self.access_key, secret_key=self.secret_key,
                          region=self.region, host=self.host, path=_PATH,
                          target=_TARGET, payload=payload)
        resp = self._client.post(f"https://{self.host}{_PATH}", headers=headers, content=payload)
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_offers(self, *, keyword=None, category=None, limit=10, since=None
                     ) -> Iterator[FetchResult]:
        payload = self._payload(keyword or category or "gift", limit)
        resp = self._post(payload)
        fetched_at = datetime.now(UTC)
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        yield FetchResult(offers=self.parse_items(body, fetched_at),
                          raw_request={"path": _PATH, "keyword": keyword},
                          raw_response=body, http_status=resp.status_code, cost_usd=0.0)

    def health(self) -> bool:
        try:
            return next(self.fetch_offers(keyword="book", limit=1)).http_status == 200
        except Exception as exc:  # noqa: BLE001
            log.warning("amazon.health_failed", error=str(exc))
            return False

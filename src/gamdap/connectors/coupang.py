"""쿠팡 파트너스 OpenAPI 커넥터(M1).

인증: CEA(HmacSHA256) 서명.
    message   = signed_date + METHOD + path + query
    signed_date = UTC 시각, 포맷 "%y%m%dT%H%M%SZ" (예: 260713T091500Z)
    Authorization: CEA algorithm=HmacSHA256, access-key={AK}, signed-date={dt}, signature={hex}

공식 문서의 서명 알고리즘을 그대로 구현한다. 서명 함수는 `now` 주입으로 결정론적 테스트 가능.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from gamdap.config import get_settings
from gamdap.connectors.base import BaseConnector, FetchResult, RateLimit, TermsPolicy
from gamdap.domain.enums import BillingType, DataSource, StockStatus
from gamdap.domain.schemas import RawOffer
from gamdap.logging import get_logger

log = get_logger("connector.coupang")

_SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search"

# 쿠팡 파트너스 문서 기반 카테고리 기본 수수료(정산 정책, per-product 미제공분 보정)
# 정확한 정산율은 core.commission_rules 로 갱신·override 된다.
_DEFAULT_COMMISSION_RAW = "3%"


def sign_request(
    method: str, path_with_query: str, secret_key: str, access_key: str,
    now: datetime | None = None,
) -> tuple[str, str]:
    """CEA Authorization 헤더 값과 signed_date 를 생성.

    Returns: (authorization_header, signed_date)
    """
    dt = (now or datetime.now(UTC)).strftime("%y%m%dT%H%M%SZ")
    path, _, query = path_with_query.partition("?")
    message = dt + method.upper() + path + query
    signature = hmac.new(
        secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    authorization = (
        f"CEA algorithm=HmacSHA256, access-key={access_key}, "
        f"signed-date={dt}, signature={signature}"
    )
    return authorization, dt


class CoupangConnector(BaseConnector):
    code = "coupang_partners"
    adapter = "coupang"

    def __init__(
        self, access_key: str | None = None, secret_key: str | None = None,
        base_url: str | None = None, sub_id: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        s = get_settings()
        self.access_key = access_key or s.coupang_access_key
        self.secret_key = secret_key or s.coupang_secret_key
        self.base_url = (base_url or s.coupang_base_url).rstrip("/")
        self.sub_id = sub_id or s.coupang_subid
        self._client = client or httpx.Client(timeout=15.0)

    def rate_limit(self) -> RateLimit:
        # 쿠팡 파트너스는 시간당 호출 제한이 있어 보수적으로.
        return RateLimit(requests_per_minute=50, burst=5)

    def terms_policy(self) -> TermsPolicy:
        return TermsPolicy(
            scraping_allowed=False, official_api_only=True, deeplink_required=True,
            notes="쿠팡 파트너스: OpenAPI/딥링크만 사용. 가격 임의 표기·스크래핑 금지.",
        )

    def _authed_headers(self, method: str, path_with_query: str) -> dict[str, str]:
        if not self.access_key or not self.secret_key:
            raise RuntimeError("쿠팡 파트너스 자격증명 미설정 (GAMDAP_COUPANG_*)")
        auth, _ = sign_request(method, path_with_query, self.secret_key, self.access_key)
        return {"Authorization": auth, "Content-Type": "application/json;charset=UTF-8"}

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _get(self, path_with_query: str) -> httpx.Response:
        headers = self._authed_headers("GET", path_with_query)
        resp = self._client.get(self.base_url + path_with_query, headers=headers)
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()  # 재시도 트리거
        return resp

    def health(self) -> bool:
        try:
            res = next(self.fetch_offers(keyword="노트북", limit=1), None)
            return bool(res and res.http_status == 200)
        except Exception as exc:  # noqa: BLE001
            log.warning("coupang.health_failed", error=str(exc))
            return False

    def fetch_offers(
        self, *, keyword: str | None = None, category: str | None = None,
        limit: int = 50, since: datetime | None = None,
    ) -> Iterator[FetchResult]:
        kw = keyword or category or "베스트"
        query = f"?keyword={httpx.QueryParams({'keyword': kw})['keyword']}&limit={min(limit, 100)}"
        if self.sub_id:
            query += f"&subId={self.sub_id}"
        path_with_query = _SEARCH_PATH + query

        resp = self._get(path_with_query)
        fetched_at = datetime.now(UTC)
        body: dict = {}
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            body = {"_raw": resp.text}

        offers: list[RawOffer] = []
        data = (body or {}).get("data") or {}
        products = data.get("productData") or []
        for idx, p in enumerate(products, start=1):
            price = p.get("productPrice")
            offers.append(
                RawOffer(
                    network_code=self.code,
                    external_product_id=str(p.get("productId")),
                    title=str(p.get("productName", "")),
                    landing_url=p.get("productUrl"),
                    thumbnail_url=p.get("productImage"),
                    price_amount=Decimal(str(price)) if price is not None else None,
                    price_currency="KRW",
                    billing_type=BillingType.CPS,
                    commission_raw=_DEFAULT_COMMISSION_RAW,
                    stock_status=StockStatus.IN_STOCK,
                    native_rank=p.get("rank", idx),
                    native_metric={
                        "isRocket": p.get("isRocket"),
                        "isFreeShipping": p.get("isFreeShipping"),
                        "categoryName": p.get("categoryName"),
                    },
                    raw_category=p.get("categoryName"),
                    data_source=DataSource.OFFICIAL_API,
                    fetched_at=fetched_at,
                )
            )

        yield FetchResult(
            offers=offers,
            raw_request={"path": _SEARCH_PATH, "keyword": kw, "limit": limit},
            raw_response=body,
            http_status=resp.status_code,
            cost_usd=0.0,
        )

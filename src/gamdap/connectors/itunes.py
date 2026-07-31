"""Apple iTunes Search 커넥터(키리스) — 실제 라이브 상품 데이터 추출.

소스: https://itunes.apple.com/search (Apple 공개 검색 API, 인증 불필요).
전 세계 실제 앱·음악·영화·전자책을 실가격·평점·아트워크·스토어링크와 함께 반환한다.
→ 앱(app_install)·디지털(digital_product) 오퍼 유형의 '진짜' 데이터 원천.

Apple 제휴(Performance Partners)는 CPS 구조이므로 유료 항목에 대표 수수료율을 부여한다.
운영에서 회원이 자신의 Apple 제휴 토큰을 연결하면 landing_url 에 제휴 파라미터가 주입된다.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from gamdap.connectors.base import BaseConnector, FetchResult, RateLimit, TermsPolicy
from gamdap.domain.enums import BillingType, CommissionKind, DataSource, OfferType, StockStatus
from gamdap.domain.schemas import RawOffer
from gamdap.logging import get_logger

log = get_logger("connector.itunes")

_BASE = "https://itunes.apple.com"
_COUNTRY = "KR"
_AFFILIATE_RATE = Decimal("0.07")  # Apple 제휴 대표 수수료율(유료 항목)

# (검색어, media, offer_type) — 키워드 미지정 시 광범위 실카탈로그 수집.
# media 유형을 교차 배치해 앱·음악·영화·전자책이 고르게 수집되도록 한다.
_DEFAULT_QUERIES: list[tuple[str, str, str]] = [
    # ── software / 앱 (app_install) ──
    ("productivity", "software", "app_install"), ("finance", "software", "app_install"),
    ("health fitness", "software", "app_install"), ("photo video", "software", "app_install"),
    ("games", "software", "app_install"), ("shopping", "software", "app_install"),
    ("education", "software", "app_install"), ("travel", "software", "app_install"),
    ("music", "software", "app_install"), ("social networking", "software", "app_install"),
    ("business", "software", "app_install"), ("food drink", "software", "app_install"),
    ("weather", "software", "app_install"), ("news", "software", "app_install"),
    ("utilities", "software", "app_install"), ("lifestyle", "software", "app_install"),
    ("navigation", "software", "app_install"), ("medical", "software", "app_install"),
    ("sports", "software", "app_install"), ("entertainment", "software", "app_install"),
    ("developer tools", "software", "app_install"), ("book reader", "software", "app_install"),
    # ── music (digital_product) ──
    ("k-pop", "music", "digital_product"), ("pop", "music", "digital_product"),
    ("hip hop", "music", "digital_product"), ("classical", "music", "digital_product"),
    ("jazz", "music", "digital_product"), ("rock", "music", "digital_product"),
    ("r&b soul", "music", "digital_product"), ("electronic", "music", "digital_product"),
    ("country", "music", "digital_product"), ("indie", "music", "digital_product"),
    ("k-drama ost", "music", "digital_product"), ("dance", "music", "digital_product"),
    # ── movie (digital_product) ──
    ("action", "movie", "digital_product"), ("animation", "movie", "digital_product"),
    ("drama", "movie", "digital_product"), ("comedy", "movie", "digital_product"),
    ("thriller", "movie", "digital_product"), ("sci-fi", "movie", "digital_product"),
    ("documentary", "movie", "digital_product"), ("romance", "movie", "digital_product"),
    # ── ebook (digital_product) ──
    ("business", "ebook", "digital_product"), ("self improvement", "ebook", "digital_product"),
    ("productivity", "ebook", "digital_product"), ("fantasy", "ebook", "digital_product"),
    ("mystery", "ebook", "digital_product"), ("cooking", "ebook", "digital_product"),
    ("history", "ebook", "digital_product"), ("science", "ebook", "digital_product"),
    # ── podcast / audiobook (digital_product) ──
    ("technology", "podcast", "digital_product"), ("investing", "podcast", "digital_product"),
    ("english learning", "podcast", "digital_product"), ("bestseller", "audiobook", "digital_product"),
    ("motivation", "audiobook", "digital_product"),
]
_PER_QUERY = 60  # 쿼리당 상한(iTunes 최대 200) — 실카탈로그 폭 확대


def _dec(v: object) -> Decimal | None:
    if v is None:
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d if d >= 0 else None  # iTunes 는 -1.0 을 '가격없음'으로 사용


class ITunesConnector(BaseConnector):
    code = "apple_media"
    adapter = "itunes"

    def __init__(self, country: str | None = None, client: httpx.Client | None = None) -> None:
        self.country = country or _COUNTRY
        self._client = client or httpx.Client(timeout=15.0)

    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=20, burst=5)

    def terms_policy(self) -> TermsPolicy:
        return TermsPolicy(scraping_allowed=False, official_api_only=True,
                           deeplink_required=True, notes="Apple 공개 검색 API(인증 불필요, 링크 기반).")

    @staticmethod
    def parse_results(payload: dict, offer_type: str, fetched_at: datetime) -> list[RawOffer]:
        results = (payload or {}).get("results") or []
        offers: list[RawOffer] = []
        for i, p in enumerate(results):
            ext = p.get("trackId") or p.get("collectionId")
            url = p.get("trackViewUrl") or p.get("collectionViewUrl")
            title = p.get("trackName") or p.get("collectionName")
            if not ext or not url or not title:
                continue
            art = (p.get("artworkUrl100") or p.get("artworkUrl60") or "")
            art = art.replace("100x100bb", "512x512bb").replace("60x60bb", "512x512bb") or None
            price = _dec(p.get("price"))
            if price is None:
                price = _dec(p.get("trackPrice")) or _dec(p.get("collectionPrice"))
            rate = _AFFILIATE_RATE if price and price > 0 else None
            offers.append(RawOffer(
                network_code="apple_media",
                external_product_id=str(ext),
                title=str(title),
                landing_url=url,
                thumbnail_url=art,
                offer_type=OfferType(offer_type),
                price_amount=price,
                price_currency=p.get("currency"),
                billing_type=BillingType.CPS,
                commission_kind=CommissionKind.PERCENT if rate is not None else None,
                commission_rate=rate,
                commission_currency=p.get("currency") if rate is not None else None,
                stock_status=StockStatus.DIGITAL_UNLIMITED,
                native_rank=i + 1,
                native_metric={"rating": p.get("averageUserRating"),
                               "seller": p.get("sellerName") or p.get("artistName"),
                               "genre": p.get("primaryGenreName"), "source": "itunes"},
                raw_category=p.get("primaryGenreName"),
                data_source=DataSource.FEED,
                fetched_at=fetched_at,
            ))
        return offers

    @retry(retry=retry_if_exception_type(httpx.HTTPStatusError),
           wait=wait_exponential(multiplier=1, min=1, max=20),
           stop=stop_after_attempt(3), reraise=True)
    def _search(self, term: str, media: str, limit: int) -> httpx.Response:
        resp = self._client.get(_BASE + "/search", params={
            "term": term, "media": media, "country": self.country, "limit": min(limit, 200),
        })
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch_offers(self, *, keyword=None, category=None, limit=200, since=None
                     ) -> Iterator[FetchResult]:
        if keyword:
            resp = self._search(keyword, category or "software", min(limit, 200))
            body = resp.json() if resp.headers.get("content-type", "").startswith(("text/", "application")) else {}
            otype = "digital_product" if (category in ("music", "movie", "ebook")) else "app_install"
            yield FetchResult(
                offers=self.parse_results(body, otype, datetime.now(UTC)),
                raw_request={"term": keyword, "media": category or "software"},
                raw_response=body, http_status=resp.status_code, cost_usd=0.0,
            )
            return

        remaining = max(1, limit)
        for term, media, otype in _DEFAULT_QUERIES:
            if remaining <= 0:
                break
            page = min(remaining, _PER_QUERY)
            resp = self._search(term, media, page)
            body = resp.json() if resp.headers.get("content-type", "").startswith(("text/", "application")) else {}
            offers = self.parse_results(body, otype, datetime.now(UTC))
            yield FetchResult(
                offers=offers, raw_request={"term": term, "media": media},
                raw_response=body, http_status=resp.status_code, cost_usd=0.0,
            )
            remaining -= len(offers)

    def health(self) -> bool:
        try:
            return next(self.fetch_offers(keyword="music", category="software", limit=1)).http_status == 200
        except Exception as exc:  # noqa: BLE001
            log.warning("itunes.health_failed", error=str(exc))
            return False

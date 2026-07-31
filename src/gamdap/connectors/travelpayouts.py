"""Travelpayouts 커넥터 — 실 항공권 특가 카탈로그(공개 Data API).

이 파일들을 통틀어 **실제 상품 데이터를 반환하는 첫 제휴 API**다. 대부분의 제휴 API는
'내가 승인받은 오퍼'만 주는 계정 스코프라 신규계정에선 0건이지만, Travelpayouts는
Aviasales 실시간 최저가를 토큰만으로 반환하는 공개 데이터 API라 계정 스코프가 아니다.

전 세계 주요 도시 출발 노선의 최저가를 수집해 SERVICE 오퍼(항공권)로 리스트업한다.
딥링크는 제휴 마커가 있으면 수익귀속되도록 구성한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx

from gamdap.config import get_settings
from gamdap.connectors.base import BaseConnector, FetchResult, RateLimit, TermsPolicy
from gamdap.domain.enums import BillingType, DataSource, OfferType, StockStatus
from gamdap.domain.schemas import RawOffer
from gamdap.logging import get_logger

log = get_logger("connector.travelpayouts")

# 전 세계 주요 출발 도시(IATA 도시코드) — 노선 다양성 확보
_ORIGINS = [
    "SEL", "TYO", "OSA", "FUK", "PEK", "SHA", "HKG", "TPE", "BKK", "SIN",
    "KUL", "CGK", "MNL", "SGN", "HAN", "DEL", "BOM", "DXB", "IST", "MOW",
    "LON", "PAR", "FRA", "BER", "AMS", "BCN", "MAD", "ROM", "NYC", "LAX",
    "SFO", "CHI", "YTO", "SYD", "MEL",
]
_CITY_KO = {
    "SEL": "서울", "TYO": "도쿄", "OSA": "오사카", "FUK": "후쿠오카", "PEK": "베이징",
    "SHA": "상하이", "HKG": "홍콩", "TPE": "타이베이", "BKK": "방콕", "SIN": "싱가포르",
    "KUL": "쿠알라룸푸르", "CGK": "자카르타", "MNL": "마닐라", "SGN": "호치민", "HAN": "하노이",
    "DEL": "델리", "BOM": "뭄바이", "DXB": "두바이", "IST": "이스탄불", "MOW": "모스크바",
    "LON": "런던", "PAR": "파리", "FRA": "프랑크푸르트", "BER": "베를린", "AMS": "암스테르담",
    "BCN": "바르셀로나", "MAD": "마드리드", "ROM": "로마", "NYC": "뉴욕", "LAX": "로스앤젤레스",
    "SFO": "샌프란시스코", "CHI": "시카고", "YTO": "토론토", "SYD": "시드니", "MEL": "멜버른",
}


def _dec(v: object) -> Decimal | None:
    if v is None:
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d if d > 0 else None


def _city(code: str) -> str:
    return _CITY_KO.get(code, code)


class TravelpayoutsConnector(BaseConnector):
    code = "travelpayouts"
    adapter = "travelpayouts"

    def __init__(self, client: httpx.Client | None = None) -> None:
        s = get_settings()
        self.token = s.travelpayouts_token
        # 마커(제휴 수익귀속 ID)만 딥링크에 노출. API 토큰은 절대 URL 에 넣지 않는다.
        self.marker = s.travelpayouts_marker.strip()
        self.base = s.travelpayouts_base_url.rstrip("/")
        self.currency = "usd"
        self._client = client or httpx.Client(
            timeout=25.0, headers={"User-Agent": "GamdapBot/1.0", "X-Access-Token": self.token})

    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=90, burst=10)

    def terms_policy(self) -> TermsPolicy:
        return TermsPolicy(scraping_allowed=False, official_api_only=True, deeplink_required=True,
                           notes="Travelpayouts 공개 Data API. 딥링크 마커로 수익귀속.")

    def _deeplink(self, origin: str, dest: str, depart: str | None) -> str:
        """Aviasales 검색 딥링크(제휴 마커 포함)."""
        dd = ""
        if depart and len(depart) >= 10:  # YYYY-MM-DD → DDMM
            dd = depart[8:10] + depart[5:7]
        seg = f"{origin}{dd}{dest}" if dd else f"{origin}{dest}"
        url = f"https://www.aviasales.com/search/{seg}1"
        return f"{url}?marker={self.marker}" if self.marker else url

    def _to_offer(self, origin: str, dest: str, d: dict, rank: int, at: datetime) -> RawOffer | None:
        price = _dec(d.get("price"))
        if not price:
            return None
        depart = d.get("departure_at") or d.get("depart_date")
        airline = d.get("airline")
        transfers = d.get("transfers", 0)
        title = f"✈ {_city(origin)}→{_city(dest)} 항공권 (최저가)"
        return RawOffer(
            network_code=self.code,
            external_product_id=f"{origin}-{dest}-{airline or 'NA'}",
            title=title[:250],
            landing_url=self._deeplink(origin, dest, depart),
            thumbnail_url=(f"https://pics.avs.io/200/200/{airline}.png" if airline else None),
            offer_type=OfferType.SERVICE,
            price_amount=price,
            price_currency=self.currency.upper(),
            billing_type=BillingType.CPS,
            stock_status=StockStatus.IN_STOCK,
            native_rank=rank,
            native_metric={"origin": origin, "destination": dest, "airline": airline,
                           "transfers": transfers, "departure_at": depart,
                           "return_at": d.get("return_at"), "flight_number": d.get("flight_number"),
                           "source": "travelpayouts"},
            raw_category="여행·항공",
            data_source=DataSource.OFFICIAL_API,
            fetched_at=at,
        )

    def _city_directions(self, origin: str) -> httpx.Response:
        return self._client.get(f"{self.base}/v1/city-directions",
                                params={"origin": origin, "currency": self.currency, "token": self.token})

    def fetch_offers(self, *, keyword=None, category=None, limit=50, since=None
                     ) -> Iterator[FetchResult]:
        if not self.token:
            return
        at = datetime.now(UTC)
        origins = [keyword.upper()] if keyword else _ORIGINS
        remaining = max(1, limit)
        for origin in origins:
            if remaining <= 0:
                break
            try:
                resp = self._city_directions(origin)
            except httpx.HTTPError as e:
                log.warning("travelpayouts.http_error", origin=origin, err=type(e).__name__)
                continue
            body = resp.json() if resp.status_code == 200 else {}
            data = body.get("data") if isinstance(body, dict) else None
            offers: list[RawOffer] = []
            if isinstance(data, dict):
                for rank, (dest, d) in enumerate(data.items(), 1):
                    if isinstance(d, dict):
                        o = self._to_offer(origin, dest, d, rank, at)
                        if o:
                            offers.append(o)
            offers = offers[:remaining]
            remaining -= len(offers)
            yield FetchResult(offers=offers, raw_request={"origin": origin},
                              raw_response=body, http_status=resp.status_code, cost_usd=0.0)

    def health(self) -> bool:
        if not self.token:
            return False
        try:
            r = self._client.get(f"{self.base}/v1/city-directions",
                                 params={"origin": "SEL", "currency": self.currency, "token": self.token})
            return r.status_code == 200 and r.json().get("success") is True
        except (httpx.HTTPError, ValueError):
            return False

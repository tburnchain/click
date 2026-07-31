"""공개 상품페이지 크롤러(Mode A) — LUXEVIA 크롤링 기술의 Python 이식.

**허가된(robots.txt 허용) 공개 쇼핑몰 상품페이지**만 대상으로 한다. 제휴 네트워크 스크래핑
금지. 정중한 크롤링 원칙:
  · robots.txt 확인 후 Disallow 경로 회피
  · 요청 간 지연(rate limit)
  · 표준 구조화데이터 우선 추출(JSON-LD Product → OpenGraph → 휴리스틱)

추출 결과는 RawOffer 로 산출되어 기존 정규화→UPSERT 파이프라인으로 리스팅된다.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from gamdap.domain.enums import BillingType, DataSource, OfferType, StockStatus
from gamdap.domain.schemas import RawOffer
from gamdap.logging import get_logger

log = get_logger("connector.webcrawler")

_UA = "GamdapBot/1.0 (+https://gamdap.example/bot; respects robots.txt)"
_JSONLD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
_OG = re.compile(r'<meta[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']', re.I)
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_PRICE_CLASS = re.compile(r'class=["\'][^"\']*price[^"\']*["\'][^>]*>\s*([£$€₩]|USD|EUR|KRW|GBP)?\s*([\d.,]+)', re.I)
_HREF = re.compile(r'href=["\']([^"\']+)["\']', re.I)
_CUR_SYM = {"£": "GBP", "$": "USD", "€": "EUR", "₩": "KRW"}
_TAG = re.compile(r"<[^>]+>")


def _text(s: str) -> str:
    return _TAG.sub("", s or "").strip()


def _num(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def _find_product_ld(obj: object) -> dict | None:
    """JSON-LD에서 @type Product 노드 탐색(@graph/list 포함)."""
    if isinstance(obj, list):
        for it in obj:
            r = _find_product_ld(it)
            if r:
                return r
    elif isinstance(obj, dict):
        t = obj.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(str(x).lower() == "product" for x in types):
            return obj
        if "@graph" in obj:
            return _find_product_ld(obj["@graph"])
    return None


def extract_product(html: str, url: str) -> dict | None:
    """상품 정보 추출: JSON-LD Product → OpenGraph → 휴리스틱."""
    og = {k.lower(): v for k, v in _OG.findall(html)}
    # 1) JSON-LD Product
    for block in _JSONLD.findall(html):
        try:
            data = json.loads(block.strip())
        except (ValueError, TypeError):
            continue
        prod = _find_product_ld(data)
        if not prod:
            continue
        offers = prod.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        brand = prod.get("brand")
        brand = brand.get("name") if isinstance(brand, dict) else brand
        price = _num(str(offers.get("price", "")))
        img = prod.get("image")
        img = img[0] if isinstance(img, list) and img else img
        if prod.get("name") and price:
            return {"name": _text(str(prod["name"])), "brand": brand,
                    "price": price, "currency": (offers.get("priceCurrency") or "USD"),
                    "image": img or og.get("og:image"), "sku": prod.get("sku"),
                    "gtin": prod.get("gtin13") or prod.get("gtin"), "url": url}
    # 2) OpenGraph
    ogp = og.get("product:price:amount") or og.get("og:price:amount")
    if og.get("og:title") and ogp and _num(ogp):
        return {"name": _text(og["og:title"]), "brand": og.get("product:brand"),
                "price": _num(ogp),
                "currency": og.get("product:price:currency") or og.get("og:price:currency") or "USD",
                "image": og.get("og:image"), "sku": None, "gtin": None, "url": url}
    # 3) 휴리스틱(h1/title + price 클래스)
    name_m = _H1.search(html) or _TITLE.search(html)
    price_m = _PRICE_CLASS.search(html)
    if name_m and price_m:
        cur = _CUR_SYM.get(price_m.group(1), (price_m.group(1) or "USD").upper())
        price = _num(price_m.group(2))
        if price:
            return {"name": _text(name_m.group(1))[:200], "brand": og.get("product:brand"),
                    "price": price, "currency": cur, "image": og.get("og:image"),
                    "sku": None, "gtin": None, "url": url}
    return None


class WebCrawler:
    code = "webcrawler"
    adapter = "webcrawler"

    def __init__(self, *, delay: float = 1.0, client: httpx.Client | None = None) -> None:
        self.delay = delay
        self._client = client or httpx.Client(timeout=20.0, follow_redirects=True,
                                              headers={"User-Agent": _UA})
        self._robots: dict[str, RobotFileParser] = {}

    def _allowed(self, url: str) -> bool:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        rp = self._robots.get(origin)
        if rp is None:
            rp = RobotFileParser()
            try:
                r = self._client.get(origin + "/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                rp.parse([])
            self._robots[origin] = rp
        return rp.can_fetch(_UA, url)

    def discover(self, list_url: str, link_pattern: str, limit: int) -> list[str]:
        """리스팅/사이트맵 페이지에서 상품 URL 수집(패턴 필터)."""
        if not self._allowed(list_url):
            log.warning("webcrawler.robots_blocked", url=list_url)
            return []
        try:
            r = self._client.get(list_url)
        except httpx.HTTPError:
            return []
        pat = re.compile(link_pattern)
        urls, seen = [], set()
        for href in _HREF.findall(r.text):
            full = urljoin(list_url, href)
            if pat.search(full) and full not in seen:
                seen.add(full)
                urls.append(full)
            if len(urls) >= limit:
                break
        return urls

    def crawl(self, *, base_url: str, list_urls: list[str], link_pattern: str,
              network_code: str, limit: int = 40) -> Iterator[RawOffer]:
        """리스팅→상품URL→추출→RawOffer. robots·지연 준수."""
        product_urls: list[str] = []
        for lu in list_urls:
            product_urls.extend(self.discover(lu, link_pattern, limit - len(product_urls)))
            if len(product_urls) >= limit:
                break
        for i, u in enumerate(product_urls[:limit]):
            if not self._allowed(u):
                continue
            time.sleep(self.delay)  # 정중한 지연
            try:
                r = self._client.get(u)
            except httpx.HTTPError:
                continue
            info = extract_product(r.text, u)
            if not info:
                continue
            yield RawOffer(
                network_code=network_code,
                external_product_id=info.get("sku") or info.get("gtin") or u,
                title=(f"{info['brand']} {info['name']}" if info.get("brand") else info["name"])[:250],
                landing_url=u,
                thumbnail_url=(urljoin(u, info["image"]) if info.get("image") else None),
                offer_type=OfferType.PHYSICAL,
                price_amount=info["price"],
                price_currency=str(info["currency"]).upper()[:3],
                billing_type=BillingType.CPS,
                stock_status=StockStatus.IN_STOCK,
                native_rank=i + 1,
                native_metric={"brand": info.get("brand"), "gtin": info.get("gtin"),
                               "source": "webcrawler"},
                data_source=DataSource.FEED,
                fetched_at=datetime.now(UTC),
            )

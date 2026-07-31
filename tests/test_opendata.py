"""공개데이터(키리스) 커넥터 파싱 테스트."""

from datetime import UTC, datetime
from decimal import Decimal

from gamdap.connectors.opendata import OpenDataConnector
from gamdap.domain.enums import DataSource, StockStatus

NOW = datetime(2026, 7, 13, tzinfo=UTC)

PAYLOAD = {
    "products": [
        {"id": 1, "title": "iPhone 9", "price": 549, "stock": 94, "rating": 4.69,
         "brand": "Apple", "category": "smartphones", "thumbnail": "https://cdn/i9.jpg"},
        {"id": 2, "title": "USB Cable", "price": 5, "stock": 3, "rating": 4.9,
         "brand": "Generic", "category": "accessories", "thumbnail": "https://cdn/c.jpg"},
        {"id": 3, "title": "Rare Item", "price": 100, "stock": 0, "rating": 3.1,
         "brand": "X", "category": "misc", "thumbnail": None},
    ]
}


def test_parse_maps_real_fields():
    offers = OpenDataConnector.parse_products(PAYLOAD, NOW)
    assert len(offers) == 3
    o = offers[0]
    assert o.external_product_id == "1"
    assert o.price_amount == Decimal("549")
    assert o.price_currency == "USD"
    assert o.raw_category == "smartphones"
    assert o.data_source is DataSource.FEED
    assert o.native_metric["rating"] == 4.69


def test_stock_status_thresholds():
    offers = {o.external_product_id: o for o in OpenDataConnector.parse_products(PAYLOAD, NOW)}
    assert offers["1"].stock_status is StockStatus.IN_STOCK    # 94
    assert offers["2"].stock_status is StockStatus.LOW         # 3
    assert offers["3"].stock_status is StockStatus.OUT_OF_STOCK  # 0


def test_rank_by_rating():
    # 평점 높은 USB Cable(4.9)이 native_rank 1
    offers = {o.external_product_id: o for o in OpenDataConnector.parse_products(PAYLOAD, NOW)}
    assert offers["2"].native_rank == 1
    assert offers["1"].native_rank == 2


def test_landing_url_present():
    offers = OpenDataConnector.parse_products(PAYLOAD, NOW)
    assert all(o.landing_url and o.landing_url.startswith("http") for o in offers)


def test_empty():
    assert OpenDataConnector.parse_products({}, NOW) == []


# ── 전체 카탈로그 페이지네이션(글로벌 수집) ──
class _Resp:
    def __init__(self, body: dict):
        self._body = body
        self.status_code = 200
        self.headers = {"content-type": "application/json"}

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:  # noqa: D401
        return None


class _FakeCatalog:
    """/products?limit&skip 로 전체(TOTAL)를 페이지네이션 제공하는 가짜 클라이언트."""

    def __init__(self, total: int):
        self.total = total
        self.calls: list[dict] = []

    def get(self, url: str, params: dict) -> _Resp:
        self.calls.append(params)
        if url.endswith("/products/search"):
            return _Resp({"products": [{"id": 1, "title": params.get("q", "x"), "price": 1,
                                        "stock": 5, "rating": 4.0, "category": "c"}], "total": 1})
        skip = int(params.get("skip", 0))
        limit = int(params.get("limit", 100))
        items = [{"id": i, "title": f"P{i}", "price": i, "stock": 5, "rating": 4.0, "category": "c"}
                 for i in range(skip, min(skip + limit, self.total))]
        return _Resp({"products": items, "total": self.total})


def test_full_catalog_paginates_all():
    fake = _FakeCatalog(total=194)
    conn = OpenDataConnector(client=fake)
    results = list(conn.fetch_offers(limit=300))
    fetched = sum(len(r.offers) for r in results)
    assert fetched == 194, f"전체 194건을 모두 수집해야 함 (got {fetched})"
    # 100개 페이지로 skip 진행: 0, 100, 194(소진)에서 종료
    assert [c["skip"] for c in fake.calls][:2] == [0, 100]


def test_full_catalog_respects_limit():
    fake = _FakeCatalog(total=194)
    conn = OpenDataConnector(client=fake)
    fetched = sum(len(r.offers) for r in conn.fetch_offers(limit=50))
    assert fetched == 50  # limit 상한 준수


def test_keyword_uses_search_endpoint():
    fake = _FakeCatalog(total=194)
    conn = OpenDataConnector(client=fake)
    list(conn.fetch_offers(keyword="phone", limit=100))
    assert any("q" in c and c.get("q") == "phone" for c in fake.calls)

"""API 라우팅·응답 스키마 테스트 — FakeRepo 주입(무 DB)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from gamdap.api.app import create_app
from gamdap.api.deps import get_repo
from gamdap.api.repo import OfferFilters
from gamdap.api.schemas import (
    CategoryOut,
    ConnectorOut,
    HistoryPoint,
    JobOut,
    Money,
    NetworkOut,
    OfferListOut,
    OfferOut,
    OpportunityOut,
    ScoreOut,
    SummaryOut,
)


def _offer(oid: int, score: float) -> OfferOut:
    return OfferOut(
        id=oid, network_code="coupang_partners", network_name="쿠팡 파트너스",
        title=f"상품 {oid}", price=Money(amount=18900, currency="KRW", krw=18900, usd=13.9),
        billing_type="CPS", commission_kind="percent", commission_rate=0.03,
        stock_status="in_stock", native_rank=oid, data_source="official_api",
        fetched_at=datetime(2026, 7, 13, tzinfo=UTC),
        score=ScoreOut(profitability=score, epc=100.0, demand=0.9,
                       competition=0.3, segment="goldmine"),
    )


class FakeRepo:
    def list_offers(self, f: OfferFilters) -> OfferListOut:
        data = [_offer(1, 88.0), _offer(2, 42.0)]
        if f.network and f.network != "coupang_partners":
            data = []
        return OfferListOut(data=data, page=f.page, size=f.size, total=len(data))

    def get_offer(self, offer_id: int):
        return _offer(offer_id, 88.0) if offer_id == 1 else None

    def rankings(self, category, country, limit):
        return [_offer(1, 88.0)]

    def product_offers(self, product_id):
        return [_offer(1, 88.0), _offer(3, 70.0)]

    def summary(self):
        return SummaryOut(total_offers=2, active_networks=1, avg_epc=100.0,
                          opportunities=1, last_ingest_at=None)

    def networks(self):
        return [NetworkOut(code="coupang_partners", display_name="쿠팡 파트너스",
                           country="KR", is_active=True)]

    def categories(self):
        return [CategoryOut(slug="electronics", name_ko="가전·전자", name_en="Electronics")]

    def opportunities(self, limit):
        return [OpportunityOut(id=1, offer_id=1, title="상품 1", network_name="쿠팡 파트너스",
                               kind="commission_up", severity="high",
                               detail={"from": 0.03, "to": 0.15},
                               detected_at=datetime(2026, 7, 13, tzinfo=UTC))]

    def offer_history(self, offer_id, limit):
        return [HistoryPoint(observed_at=datetime(2026, 7, 12, tzinfo=UTC), price_amount=20000),
                HistoryPoint(observed_at=datetime(2026, 7, 13, tzinfo=UTC), price_amount=18900)]

    def connectors(self):
        return [ConnectorOut(code="opendata", display_name="공개데이터", adapter="opendata",
                             data_source="feed", healthy=True, configured=True,
                             offer_count=30, last_ingest_at=None)]

    def jobs(self, limit):
        return [JobOut(id=1, network_code="opendata", job_type="manual", status="success",
                       keyword="phone", rows_upserted=5, rows_changed=5, fetched=5)]

    def trigger_ingest(self, network, keyword, limit):
        return JobOut(id=2, network_code=network, job_type="manual", status="success",
                      keyword=keyword, rows_upserted=limit, rows_changed=limit, fetched=limit)


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_repo] = lambda: FakeRepo()
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_offers(client):
    r = client.get("/api/v1/offers")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["data"][0]["score"]["segment"] == "goldmine"
    assert body["data"][0]["price"]["krw"] == "18900.0000" or float(body["data"][0]["price"]["krw"]) == 18900


def test_offers_filter_empty(client):
    r = client.get("/api/v1/offers", params={"network": "unknown_net"})
    assert r.json()["total"] == 0


def test_get_offer_404(client):
    assert client.get("/api/v1/offers/999").status_code == 404
    assert client.get("/api/v1/offers/1").status_code == 200


def test_rankings(client):
    r = client.get("/api/v1/rankings", params={"limit": 10})
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_compare(client):
    r = client.get("/api/v1/compare", params={"product_id": 5})
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_summary(client):
    r = client.get("/api/v1/analytics/summary")
    assert r.json()["total_offers"] == 2


def test_meta(client):
    assert client.get("/api/v1/meta/networks").json()[0]["code"] == "coupang_partners"
    assert client.get("/api/v1/meta/categories").json()[0]["slug"] == "electronics"


def test_invalid_sort_rejected(client):
    r = client.get("/api/v1/offers", params={"sort": ";drop"})
    assert r.status_code == 422  # 화이트리스트 패턴 위반


def test_opportunities(client):
    r = client.get("/api/v1/analytics/opportunities")
    assert r.status_code == 200
    assert r.json()[0]["kind"] == "commission_up"


def test_offer_history(client):
    r = client.get("/api/v1/offers/1/history")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_crawl_connectors(client):
    r = client.get("/api/v1/crawl/connectors")
    assert r.status_code == 200
    assert r.json()[0]["code"] == "opendata"


def test_crawl_jobs(client):
    r = client.get("/api/v1/crawl/jobs")
    assert r.status_code == 200
    assert r.json()[0]["status"] == "success"


def test_crawl_ingest(client):
    r = client.post("/api/v1/crawl/ingest", json={"network": "opendata", "keyword": "phone", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["fetched"] == 5
    assert body["network_code"] == "opendata"

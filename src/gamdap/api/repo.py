"""데이터 접근 계층(Repository). 라우터는 Repo 프로토콜에만 의존 → 테스트 시 Fake 주입.

PgRepo: PostgreSQL 구현(연결풀 사용).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from gamdap.api.schemas import (
    CategoryOut,
    ConnectorOut,
    Facet,
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

# 정렬 화이트리스트(SQL 인젝션 방지)
_SORT_MAP = {
    "score": "ps.profitability_score",
    "epc": "ps.expected_epc",
    "commission": "o.commission_rate",
    "price": "o.price_krw",
    "freshness": "o.fetched_at",
}


@dataclass
class OfferFilters:
    network: str | None = None
    country: str | None = None
    category: str | None = None
    billing_type: str | None = None
    offer_type: str | None = None
    segment: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    q: str | None = None
    sort: str = "score"
    page: int = 1
    size: int = 20


class Repo(Protocol):
    def list_offers(self, f: OfferFilters) -> OfferListOut: ...
    def get_offer(self, offer_id: int) -> OfferOut | None: ...
    def rankings(self, category: str | None, country: str | None, limit: int) -> list[OfferOut]: ...
    def product_offers(self, product_id: int) -> list[OfferOut]: ...
    def summary(self) -> SummaryOut: ...
    def networks(self) -> list[NetworkOut]: ...
    def categories(self) -> list[CategoryOut]: ...
    def opportunities(self, limit: int) -> list[OpportunityOut]: ...
    def offer_history(self, offer_id: int, limit: int) -> list[HistoryPoint]: ...
    def connectors(self) -> list[ConnectorOut]: ...
    def jobs(self, limit: int) -> list[JobOut]: ...
    def trigger_ingest(self, network: str, keyword: str | None, limit: int) -> JobOut: ...


def _row_to_offer(r: dict) -> OfferOut:
    return OfferOut(
        id=r["id"],
        product_id=r.get("product_id"),
        network_code=r["net_code"],
        network_name=r["net_name"],
        title=r["title"],
        thumbnail_url=r.get("thumbnail_url"),
        landing_url=r.get("landing_url"),
        offer_type=r.get("offer_type") or "physical_product",
        is_sample=bool((r.get("native_metric_json") or {}).get("sample")),
        price=Money(
            amount=r.get("price_amount"), currency=r.get("price_currency"),
            krw=r.get("price_krw"), usd=r.get("price_usd"),
        ),
        billing_type=r.get("billing_type"),
        commission_kind=r.get("commission_kind"),
        commission_rate=r.get("commission_rate"),
        commission_fixed=Money(
            amount=r.get("commission_fixed_amount"), currency=r.get("commission_currency"),
        ) if r.get("commission_fixed_amount") is not None else None,
        stock_status=r.get("stock_status"),
        native_rank=r.get("native_rank"),
        data_source=r["data_source"],
        fetched_at=r["fetched_at"],
        score=ScoreOut(
            profitability=float(r["profitability_score"]) if r.get("profitability_score") is not None else None,
            epc=float(r["expected_epc"]) if r.get("expected_epc") is not None else None,
            demand=float(r["demand_index"]) if r.get("demand_index") is not None else None,
            competition=float(r["competition_index"]) if r.get("competition_index") is not None else None,
            segment=r.get("segment"),
        ),
    )


_BASE_SELECT = """
    SELECT o.id, o.product_id, o.title, o.thumbnail_url, o.landing_url,
           o.offer_type, o.native_metric_json,
           o.price_amount, o.price_currency, o.price_krw, o.price_usd,
           o.billing_type, o.commission_kind, o.commission_rate,
           o.commission_fixed_amount, o.commission_currency,
           o.stock_status, o.native_rank, o.data_source, o.fetched_at,
           n.code AS net_code, n.display_name AS net_name,
           ps.profitability_score, ps.expected_epc, ps.demand_index, ps.competition_index,
           pc.segment
    FROM core.offers o
    JOIN core.networks n ON n.id = o.network_id
    LEFT JOIN analytics.profitability_scores ps ON ps.offer_id = o.id
    LEFT JOIN analytics.product_classifications pc ON pc.offer_id = o.id
    LEFT JOIN core.products p ON p.id = o.product_id
    LEFT JOIN core.categories c ON c.id = p.category_id
    LEFT JOIN core.countries co ON co.id = n.home_country_id
"""


class PgRepo:
    """PostgreSQL 구현."""

    def _conn(self):  # noqa: ANN202
        from gamdap.db import get_pool

        return get_pool().connection()

    def _where(self, f: OfferFilters) -> tuple[str, dict]:
        clauses = ["o.is_active"]
        params: dict = {}
        if f.network:
            clauses.append("n.code = %(network)s")
            params["network"] = f.network
        if f.country:
            clauses.append("co.iso_code = %(country)s")
            params["country"] = f.country
        if f.category:
            clauses.append("c.path <@ (SELECT path FROM core.categories WHERE slug = %(category)s)")
            params["category"] = f.category
        if f.billing_type:
            clauses.append("o.billing_type = %(billing_type)s")
            params["billing_type"] = f.billing_type
        if f.offer_type:
            clauses.append("o.offer_type = %(offer_type)s")
            params["offer_type"] = f.offer_type
        if f.segment:
            clauses.append("pc.segment = %(segment)s")
            params["segment"] = f.segment
        if f.min_price is not None:
            clauses.append("o.price_krw >= %(min_price)s")
            params["min_price"] = f.min_price
        if f.max_price is not None:
            clauses.append("o.price_krw <= %(max_price)s")
            params["max_price"] = f.max_price
        if f.q:
            # 전문검색(FTS) OR 퍼지(트라이그램, 오타 허용)
            clauses.append(
                "(o.search_tsv @@ websearch_to_tsquery('simple', %(q)s) "
                "OR similarity(o.title, %(q)s) > 0.15)"
            )
            params["q"] = f.q
        return " AND ".join(clauses), params

    # 관련도 = 전문검색 랭크 + 문자열 유사도
    _REL = ("(ts_rank(o.search_tsv, websearch_to_tsquery('simple', %(q)s)) "
            "+ similarity(o.title, %(q)s))")

    def _facets(self, conn, where: str, params: dict) -> dict[str, list[Facet]]:  # noqa: ANN001
        base = (
            "FROM core.offers o JOIN core.networks n ON n.id=o.network_id "
            "LEFT JOIN core.products p ON p.id=o.product_id "
            "LEFT JOIN core.categories c ON c.id=p.category_id "
            "LEFT JOIN core.countries co ON co.id=n.home_country_id "
            "LEFT JOIN analytics.product_classifications pc ON pc.offer_id=o.id "
            f"WHERE {where}"
        )
        nets = conn.execute(
            f"SELECT n.code AS k, count(*) AS c {base} GROUP BY n.code ORDER BY c DESC", params
        ).fetchall()
        segs = conn.execute(
            f"SELECT pc.segment AS k, count(*) AS c {base} "
            "AND pc.segment IS NOT NULL GROUP BY pc.segment ORDER BY c DESC", params
        ).fetchall()
        return {
            "network": [Facet(key=r["k"], count=r["c"]) for r in nets],
            "segment": [Facet(key=r["k"], count=r["c"]) for r in segs],
        }

    def list_offers(self, f: OfferFilters) -> OfferListOut:
        where, params = self._where(f)
        size = max(1, min(f.size, 100))
        offset = (max(1, f.page) - 1) * size

        # 정렬: 검색어가 있고 relevance면 관련도 랭킹, 아니면 지정 컬럼
        if f.q and f.sort in ("relevance", "score"):
            order = f"{self._REL} DESC, ps.profitability_score DESC NULLS LAST, o.id DESC"
        else:
            order = f"{_SORT_MAP.get(f.sort, _SORT_MAP['score'])} DESC NULLS LAST, o.id DESC"

        with self._conn() as conn:
            total = conn.execute(
                f"SELECT count(*) AS c FROM core.offers o "
                f"JOIN core.networks n ON n.id=o.network_id "
                f"LEFT JOIN core.products p ON p.id=o.product_id "
                f"LEFT JOIN core.categories c ON c.id=p.category_id "
                f"LEFT JOIN core.countries co ON co.id=n.home_country_id "
                f"LEFT JOIN analytics.product_classifications pc ON pc.offer_id=o.id "
                f"WHERE {where}", params,
            ).fetchone()["c"]
            rows = conn.execute(
                f"{_BASE_SELECT} WHERE {where} ORDER BY {order} "
                f"LIMIT %(_size)s OFFSET %(_offset)s",
                {**params, "_size": size, "_offset": offset},
            ).fetchall()
            facets = self._facets(conn, where, params)
        return OfferListOut(
            data=[_row_to_offer(r) for r in rows],
            page=f.page, size=size, total=total, facets=facets,
        )

    def get_offer(self, offer_id: int) -> OfferOut | None:
        with self._conn() as conn:
            r = conn.execute(f"{_BASE_SELECT} WHERE o.id = %s", (offer_id,)).fetchone()
        return _row_to_offer(r) if r else None

    def rankings(self, category: str | None, country: str | None, limit: int) -> list[OfferOut]:
        f = OfferFilters(category=category, country=country, sort="score", size=min(limit, 100))
        return self.list_offers(f).data

    def product_offers(self, product_id: int) -> list[OfferOut]:
        with self._conn() as conn:
            rows = conn.execute(
                f"{_BASE_SELECT} WHERE o.product_id = %s ORDER BY ps.profitability_score DESC NULLS LAST",
                (product_id,),
            ).fetchall()
        return [_row_to_offer(r) for r in rows]

    def summary(self) -> SummaryOut:
        with self._conn() as conn:
            r = conn.execute(
                """
                SELECT
                  (SELECT count(*) FROM core.offers WHERE is_active) AS total_offers,
                  (SELECT count(*) FROM core.networks WHERE is_active) AS active_networks,
                  (SELECT avg(expected_epc) FROM analytics.profitability_scores) AS avg_epc,
                  (SELECT count(*) FROM analytics.product_classifications
                     WHERE segment IN ('goldmine','rising')) AS opportunities,
                  (SELECT max(finished_at) FROM core.ingestion_jobs WHERE status IN ('success','partial')) AS last_ingest_at
                """
            ).fetchone()
        return SummaryOut(
            total_offers=r["total_offers"] or 0,
            active_networks=r["active_networks"] or 0,
            avg_epc=float(r["avg_epc"]) if r["avg_epc"] is not None else None,
            opportunities=r["opportunities"] or 0,
            last_ingest_at=r["last_ingest_at"],
        )

    def networks(self) -> list[NetworkOut]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT n.code, n.display_name, n.is_active, co.iso_code AS country "
                "FROM core.networks n LEFT JOIN core.countries co ON co.id=n.home_country_id "
                "ORDER BY n.display_name"
            ).fetchall()
        return [NetworkOut(code=r["code"], display_name=r["display_name"],
                           country=r["country"], is_active=r["is_active"]) for r in rows]

    def categories(self) -> list[CategoryOut]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT slug, name_ko, name_en FROM core.categories ORDER BY path"
            ).fetchall()
        return [CategoryOut(slug=r["slug"], name_ko=r["name_ko"], name_en=r["name_en"]) for r in rows]

    def opportunities(self, limit: int) -> list[OpportunityOut]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT e.id, e.offer_id, e.kind, e.severity, e.detail, e.detected_at,
                       o.title, n.display_name AS net_name
                FROM core.opportunity_events e
                JOIN core.offers o ON o.id = e.offer_id
                JOIN core.networks n ON n.id = o.network_id
                ORDER BY e.detected_at DESC LIMIT %s
                """,
                (min(limit, 200),),
            ).fetchall()
        return [
            OpportunityOut(
                id=r["id"], offer_id=r["offer_id"], title=r["title"], network_name=r["net_name"],
                kind=r["kind"], severity=r["severity"], detail=r["detail"], detected_at=r["detected_at"],
            )
            for r in rows
        ]

    def offer_history(self, offer_id: int, limit: int) -> list[HistoryPoint]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT observed_at, price_amount, commission_rate, stock_status "
                "FROM core.price_history WHERE offer_id=%s "
                "ORDER BY observed_at DESC LIMIT %s",
                (offer_id, min(limit, 500)),
            ).fetchall()
        return [
            HistoryPoint(
                observed_at=r["observed_at"], price_amount=r["price_amount"],
                commission_rate=r["commission_rate"], stock_status=r["stock_status"],
            )
            for r in reversed(rows)
        ]

    def connectors(self) -> list[ConnectorOut]:
        from gamdap.connectors import get_connector

        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT n.code, n.display_name, n.adapter, n.data_source,
                       (SELECT count(*) FROM core.offers o WHERE o.network_id=n.id) AS offer_count,
                       (SELECT max(finished_at) FROM core.ingestion_jobs j
                          WHERE j.network_code=n.code AND j.status IN ('success','partial')) AS last_ingest
                FROM core.networks n WHERE n.is_active ORDER BY n.display_name
                """
            ).fetchall()
        out: list[ConnectorOut] = []
        for r in rows:
            healthy, configured = False, False
            if r["adapter"]:
                try:
                    conn_obj = get_connector(r["adapter"])
                    configured = True
                    healthy = bool(conn_obj.health())
                except Exception:  # noqa: BLE001
                    healthy = False
            out.append(ConnectorOut(
                code=r["code"], display_name=r["display_name"], adapter=r["adapter"],
                data_source=r["data_source"], healthy=healthy, configured=configured,
                offer_count=r["offer_count"] or 0, last_ingest_at=r["last_ingest"],
            ))
        return out

    def jobs(self, limit: int) -> list[JobOut]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, network_code, job_type, status, params, "
                "rows_upserted, rows_changed, started_at, finished_at, error "
                "FROM core.ingestion_jobs ORDER BY started_at DESC LIMIT %s",
                (min(limit, 200),),
            ).fetchall()
        return [
            JobOut(
                id=r["id"], network_code=r["network_code"] or "", job_type=r["job_type"] or "",
                status=r["status"], keyword=(r["params"] or {}).get("keyword"),
                rows_upserted=r["rows_upserted"] or 0, rows_changed=r["rows_changed"] or 0,
                started_at=r["started_at"], finished_at=r["finished_at"], error=r["error"],
            )
            for r in rows
        ]

    def trigger_ingest(self, network: str, keyword: str | None, limit: int) -> JobOut:
        from gamdap.ingest import run_ingestion

        rep = run_ingestion(network, keyword=keyword, limit=limit, job_type="manual")
        return JobOut(
            id=rep.job_id or 0, network_code=network, job_type="manual", status=rep.status,
            keyword=keyword, rows_upserted=rep.stats.upserted, rows_changed=rep.stats.changed,
            fetched=rep.fetched, error="; ".join(rep.errors[:3]) or None,
        )

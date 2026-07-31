"""멱등 UPSERT(설계 부록 A) — 변경분만 반영, 이력은 트리거가 적재.

RETURNING (xmax = 0) 로 INSERT/UPDATE 를 구분한다:
    xmax = 0  → 신규 INSERT
    xmax ≠ 0  → 실제 UPDATE(값 변경)
    반환 없음  → 충돌+무변경(스킵)
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import Connection

from gamdap.domain.schemas import NormalizedOffer

_UPSERT_SQL = """
INSERT INTO core.offers (
    network_id, external_product_id, title, landing_url, thumbnail_url, offer_type,
    price_amount, price_currency, price_krw, price_usd,
    billing_type, commission_kind, commission_rate, commission_fixed_amount, commission_currency,
    stock_status, stock_quantity, native_rank, native_metric_json, raw_category,
    data_source, fetched_at, raw_ref, needs_review
) VALUES (
    %(network_id)s, %(external_product_id)s, %(title)s, %(landing_url)s, %(thumbnail_url)s,
    %(offer_type)s,
    %(price_amount)s, %(price_currency)s, %(price_krw)s, %(price_usd)s,
    %(billing_type)s, %(commission_kind)s, %(commission_rate)s, %(commission_fixed_amount)s,
    %(commission_currency)s,
    %(stock_status)s, %(stock_quantity)s, %(native_rank)s, %(native_metric_json)s, %(raw_category)s,
    %(data_source)s, %(fetched_at)s, %(raw_ref)s, %(needs_review)s
)
ON CONFLICT (network_id, external_product_id) DO UPDATE SET
    title              = EXCLUDED.title,
    landing_url        = EXCLUDED.landing_url,
    thumbnail_url      = EXCLUDED.thumbnail_url,
    offer_type         = EXCLUDED.offer_type,
    price_amount       = EXCLUDED.price_amount,
    price_currency     = EXCLUDED.price_currency,
    price_krw          = EXCLUDED.price_krw,
    price_usd          = EXCLUDED.price_usd,
    billing_type       = EXCLUDED.billing_type,
    commission_kind    = EXCLUDED.commission_kind,
    commission_rate    = EXCLUDED.commission_rate,
    commission_fixed_amount = EXCLUDED.commission_fixed_amount,
    commission_currency= EXCLUDED.commission_currency,
    stock_status       = EXCLUDED.stock_status,
    stock_quantity     = EXCLUDED.stock_quantity,
    native_rank        = EXCLUDED.native_rank,
    native_metric_json = EXCLUDED.native_metric_json,
    raw_category       = EXCLUDED.raw_category,
    fetched_at         = EXCLUDED.fetched_at,
    needs_review       = EXCLUDED.needs_review
WHERE
    core.offers.price_amount            IS DISTINCT FROM EXCLUDED.price_amount
 OR core.offers.commission_rate         IS DISTINCT FROM EXCLUDED.commission_rate
 OR core.offers.commission_fixed_amount IS DISTINCT FROM EXCLUDED.commission_fixed_amount
 OR core.offers.stock_status           IS DISTINCT FROM EXCLUDED.stock_status
 OR core.offers.stock_quantity          IS DISTINCT FROM EXCLUDED.stock_quantity
 OR core.offers.title                   IS DISTINCT FROM EXCLUDED.title
 OR core.offers.native_rank             IS DISTINCT FROM EXCLUDED.native_rank
RETURNING (xmax = 0) AS inserted;
"""


@dataclass
class UpsertStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def upserted(self) -> int:
        return self.inserted + self.updated

    @property
    def changed(self) -> int:
        return self.inserted + self.updated


def _params(o: NormalizedOffer) -> dict:
    import json

    d = o.model_dump(mode="python")
    # enum → str, dict → json 문자열(psycopg jsonb 어댑터가 있으면 dict 그대로도 가능하나 안전하게)
    for k in ("offer_type", "billing_type", "commission_kind", "stock_status", "data_source"):
        v = d.get(k)
        d[k] = str(v) if v is not None else None
    d["native_metric_json"] = json.dumps(o.native_metric_json, ensure_ascii=False)
    return d


def upsert_offers(conn: Connection, offers: list[NormalizedOffer]) -> UpsertStats:
    """오퍼 리스트를 멱등 UPSERT(행 단위). 통계 반환. 소량·명확성용."""
    stats = UpsertStats()
    for o in offers:
        row = conn.execute(_UPSERT_SQL, _params(o)).fetchone()
        if row is None:
            stats.unchanged += 1
        elif row["inserted"]:
            stats.inserted += 1
        else:
            stats.updated += 1
    return stats


# 벌크 UPSERT용 컬럼 순서(대량 수집 효율)
_COLS = [
    "network_id", "external_product_id", "title", "landing_url", "thumbnail_url", "offer_type",
    "price_amount", "price_currency", "price_krw", "price_usd",
    "billing_type", "commission_kind", "commission_rate", "commission_fixed_amount",
    "commission_currency", "stock_status", "stock_quantity", "native_rank",
    "native_metric_json", "raw_category", "data_source", "fetched_at", "raw_ref", "needs_review",
]


def _row_tuple(o: NormalizedOffer) -> tuple:
    p = _params(o)
    return tuple(p[c] for c in _COLS)


def bulk_upsert_offers(conn: Connection, offers: list[NormalizedOffer],
                       chunk: int = 500) -> UpsertStats:
    """다중 VALUES 단일 왕복 + 청킹 벌크 UPSERT. 대량 수집에서 행 단위 대비 수십 배.

    파라미터 상한(65535)을 넘지 않도록 chunk(기본 500행 × 23컬럼 = 11,500) 유지.
    """
    stats = UpsertStats()
    if not offers:
        return stats
    cols_sql = ", ".join(_COLS)
    placeholder = "(" + ",".join(["%s"] * len(_COLS)) + ")"
    for i in range(0, len(offers), chunk):
        batch = offers[i:i + chunk]
        values_sql = ",".join([placeholder] * len(batch))
        params: list = [v for o in batch for v in _row_tuple(o)]
        sql = (
            f"INSERT INTO core.offers ({cols_sql}) VALUES {values_sql} "
            "ON CONFLICT (network_id, external_product_id) DO UPDATE SET "
            "title=EXCLUDED.title, landing_url=EXCLUDED.landing_url, "
            "thumbnail_url=EXCLUDED.thumbnail_url, offer_type=EXCLUDED.offer_type, "
            "price_amount=EXCLUDED.price_amount, "
            "price_currency=EXCLUDED.price_currency, price_krw=EXCLUDED.price_krw, "
            "price_usd=EXCLUDED.price_usd, billing_type=EXCLUDED.billing_type, "
            "commission_kind=EXCLUDED.commission_kind, commission_rate=EXCLUDED.commission_rate, "
            "commission_fixed_amount=EXCLUDED.commission_fixed_amount, "
            "commission_currency=EXCLUDED.commission_currency, stock_status=EXCLUDED.stock_status, "
            "stock_quantity=EXCLUDED.stock_quantity, native_rank=EXCLUDED.native_rank, "
            "native_metric_json=EXCLUDED.native_metric_json, raw_category=EXCLUDED.raw_category, "
            "fetched_at=EXCLUDED.fetched_at, needs_review=EXCLUDED.needs_review "
            "WHERE core.offers.price_amount IS DISTINCT FROM EXCLUDED.price_amount "
            "OR core.offers.commission_rate IS DISTINCT FROM EXCLUDED.commission_rate "
            "OR core.offers.commission_fixed_amount IS DISTINCT FROM EXCLUDED.commission_fixed_amount "
            "OR core.offers.stock_status IS DISTINCT FROM EXCLUDED.stock_status "
            "OR core.offers.stock_quantity IS DISTINCT FROM EXCLUDED.stock_quantity "
            "OR core.offers.title IS DISTINCT FROM EXCLUDED.title "
            "OR core.offers.native_rank IS DISTINCT FROM EXCLUDED.native_rank "
            "RETURNING (xmax = 0) AS inserted"
        )
        rows = conn.execute(sql, params).fetchall()
        ins = sum(1 for r in rows if r["inserted"])
        stats.inserted += ins
        stats.updated += len(rows) - ins
        stats.unchanged += len(batch) - len(rows)
    return stats


def insert_raw_payload(
    conn: Connection, network_code: str, source: str,
    request: dict, response: dict | None, http_status: int | None, cost_usd: float,
) -> int:
    """Bronze 원본 적재. 응답은 zstd 압축(bytea)으로 저장 → 저장공간 대폭 절감. id 반환."""
    import json

    from gamdap.storage.compression import compress_json

    response_zstd = orig = comp = None
    if response is not None:
        raw = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        blob = compress_json(response)
        response_zstd, orig, comp = blob, len(raw), len(blob)

    row = conn.execute(
        """
        INSERT INTO bronze.raw_payloads
            (network_code, source, request, response_zstd, orig_bytes, comp_bytes,
             http_status, cost_usd)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (network_code, source, json.dumps(request, ensure_ascii=False),
         response_zstd, orig, comp, http_status, cost_usd),
    ).fetchone()
    return int(row["id"])

"""수집 오케스트레이션: 커넥터 → Bronze 적재 → 정규화 → 멱등 UPSERT → 작업 로깅.

멱등성: 같은 수집을 두 번 돌려도 최종 상태 동일(자연키 UPSERT + 변경분만 이력).
격리: 오퍼 단위 정규화 실패가 배치를 죽이지 않도록 예외를 needs_review 로 흡수.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from psycopg import Connection

from gamdap.connectors import get_connector
from gamdap.db import transaction
from gamdap.ingest.normalizer import normalize_offer
from gamdap.ingest.upsert import UpsertStats, bulk_upsert_offers, insert_raw_payload
from gamdap.logging import get_logger
from gamdap.normalize.category_map import resolve_category_id
from gamdap.normalize.currency import CurrencyConverter
from gamdap.runtime import get_guard

log = get_logger("ingest.pipeline")


@dataclass
class IngestionReport:
    network_code: str
    job_id: int | None = None
    fetched: int = 0
    stats: UpsertStats = field(default_factory=UpsertStats)
    errors: list[str] = field(default_factory=list)
    status: str = "running"


def _network_id(conn: Connection, code: str) -> int:
    row = conn.execute("SELECT id FROM core.networks WHERE code = %s", (code,)).fetchone()
    if row is None:
        raise RuntimeError(f"네트워크 미등록: {code} (마이그레이션 0005 시드 확인)")
    return int(row["id"])


def _network_adapter(conn: Connection, code: str) -> str:
    row = conn.execute("SELECT adapter FROM core.networks WHERE code = %s", (code,)).fetchone()
    if row is None or not row["adapter"]:
        raise RuntimeError(f"네트워크 adapter 미설정: {code}")
    return str(row["adapter"])


def _start_job(conn: Connection, code: str, job_type: str, params: dict) -> int:
    import json

    row = conn.execute(
        "INSERT INTO core.ingestion_jobs (network_code, job_type, status, params) "
        "VALUES (%s, %s, 'running', %s) RETURNING id",
        (code, job_type, json.dumps(params, ensure_ascii=False)),
    ).fetchone()
    return int(row["id"])


def _finish_job(conn: Connection, job_id: int, report: IngestionReport) -> None:
    conn.execute(
        "UPDATE core.ingestion_jobs SET status=%s, rows_upserted=%s, rows_changed=%s, "
        "finished_at=%s, error=%s WHERE id=%s",
        (report.status, report.stats.upserted, report.stats.changed,
         datetime.now(UTC), "; ".join(report.errors[:5]) or None, job_id),
    )


def run_ingestion(
    network_code: str, *, keyword: str | None = None, category: str | None = None,
    limit: int = 50, job_type: str = "incremental",
) -> IngestionReport:
    """단일 네트워크 수집 실행."""
    report = IngestionReport(network_code=network_code)

    with transaction() as conn:
        network_id = _network_id(conn, network_code)
        adapter = _network_adapter(conn, network_code)
        converter = CurrencyConverter.load_latest(conn)
        report.job_id = _start_job(
            conn, network_code, job_type,
            {"keyword": keyword, "category": category, "limit": limit},
        )

    connector = get_connector(adapter)

    # 부하 안정화 가드(커넥터별 레이트리밋 + 서킷브레이커)
    rl = connector.rate_limit()
    guard = get_guard(network_code, rate_per_sec=rl.requests_per_minute / 60.0,
                      capacity=rl.burst)
    if not guard.before(timeout=60.0):
        report.status = "failed"
        report.errors.append(f"부하 가드 차단(서킷 {guard.breaker.state} / 레이트리밋)")
        with transaction() as conn:
            if report.job_id is not None:
                _finish_job(conn, report.job_id, report)
        log.warning("ingest.guarded", network=network_code, circuit=str(guard.breaker.state))
        return report

    try:
        for result in connector.fetch_offers(keyword=keyword, category=category, limit=limit):
            report.fetched += len(result.offers)
            with transaction() as conn:
                raw_ref = insert_raw_payload(
                    conn, network_code, f"{adapter}_api",
                    result.raw_request, result.raw_response, result.http_status, result.cost_usd,
                )
                normalized = []
                seen_categories: set[str] = set()
                for raw in result.offers:
                    try:
                        # 카테고리 매핑 학습(§5.3): 배치 내 유니크 원본만 1회 해소
                        if raw.raw_category and raw.raw_category not in seen_categories:
                            seen_categories.add(raw.raw_category)
                            resolve_category_id(conn, network_id, raw.raw_category)
                        normalized.append(normalize_offer(raw, network_id, converter, raw_ref))
                    except Exception as exc:  # noqa: BLE001 — 행 단위 격리
                        report.errors.append(f"{raw.external_product_id}: {exc}")
                batch = bulk_upsert_offers(conn, normalized)
                report.stats.inserted += batch.inserted
                report.stats.updated += batch.updated
                report.stats.unchanged += batch.unchanged
        report.status = "partial" if report.errors else "success"
        guard.success()
    except Exception as exc:  # noqa: BLE001
        report.status = "failed"
        report.errors.append(str(exc))
        guard.failure()
        log.error("ingest.failed", network=network_code, error=str(exc))

    with transaction() as conn:
        if report.job_id is not None:
            _finish_job(conn, report.job_id, report)

    log.info(
        "ingest.done", network=network_code, status=report.status,
        fetched=report.fetched, inserted=report.stats.inserted,
        updated=report.stats.updated, unchanged=report.stats.unchanged,
        errors=len(report.errors),
    )
    return report

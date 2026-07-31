"""Celery 워커 · 스케줄러(설계 §6.2) — 주기적 수집·계산 파이프라인.

실행: celery -A gamdap.worker.celery_app worker -B --loglevel=INFO
(-B 는 beat 내장. 프로덕션은 worker/beat 분리 권장.)
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from gamdap.config import get_settings
from gamdap.logging import get_logger

log = get_logger("worker")
settings = get_settings()

celery_app = Celery("gamdap", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_acks_late=True,
    worker_max_tasks_per_child=200,
)


# ── 태스크 ─────────────────────────────────────────────

@celery_app.task(name="gamdap.fx_sync")
def fx_sync(provider: str = "ecb") -> int:
    from gamdap.db import transaction
    from gamdap.normalize.fx_source import sync_exchange_rates

    with transaction() as conn:
        return sync_exchange_rates(conn, provider=provider)


@celery_app.task(name="gamdap.ingest", bind=True, max_retries=3)
def ingest(self, network_code: str, keyword: str | None = None, limit: int = 50) -> dict:  # noqa: ANN001
    from gamdap.ingest import run_ingestion

    try:
        r = run_ingestion(network_code, keyword=keyword, limit=limit)
        return {"status": r.status, "inserted": r.stats.inserted, "updated": r.stats.updated}
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=30) from exc


@celery_app.task(name="gamdap.pipeline")
def run_pipeline() -> dict:
    """수집 후처리 파이프라인: 엔티티해소 → 점수 → 분류 → 변동감지."""
    from gamdap.analytics.classification import compute_classifications
    from gamdap.analytics.opportunities import scan_opportunities
    from gamdap.analytics.profitability import compute_scores
    from gamdap.db import transaction
    from gamdap.ingest.entity_resolution import resolve_products

    out: dict = {}
    with transaction() as conn:
        out["resolved"] = resolve_products(conn).linked
    with transaction() as conn:
        out["scored"] = compute_scores(conn)
    with transaction() as conn:
        out["classified"] = compute_classifications(conn)
    with transaction() as conn:
        out["events"] = scan_opportunities(conn)
    log.info("pipeline.done", **out)
    return out


@celery_app.task(name="gamdap.maintain_partitions")
def maintain_partitions() -> dict:
    """월 파티션 선행 생성 + 보존초과 정리 (무한증가 제어)."""
    from gamdap.db import transaction
    from gamdap.db.partitions import drop_old_partitions, ensure_month_partitions

    with transaction() as conn:
        created = ensure_month_partitions(conn, months_ahead=2)
        dropped = drop_old_partitions(conn, retain_months=12)
    return {"created": len(created), "dropped": len(dropped)}


@celery_app.task(name="gamdap.scan_discovery")
def scan_discovery() -> int:
    """발견 스캔은 프로버 주입이 필요 → 프로덕션에서 실제 프로버 연결."""
    log.info("discovery.scan_skipped_no_prober")
    return 0


# ── 스케줄(설계 §6.2) ──────────────────────────────────
celery_app.conf.beat_schedule = {
    "fx-daily": {"task": "gamdap.fx_sync", "schedule": crontab(hour=8, minute=0)},
    "ingest-coupang-daily": {
        "task": "gamdap.ingest", "schedule": crontab(hour=9, minute=0),
        "args": ("coupang_partners",),
    },
    "pipeline-hourly": {"task": "gamdap.pipeline", "schedule": crontab(minute=30)},
    "partitions-daily": {"task": "gamdap.maintain_partitions", "schedule": crontab(hour=7, minute=0)},
}

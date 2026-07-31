"""월 파티션 자동 관리 — price_history·api_call_logs 무한증가 제어.

ensure_month_partitions: 당월 + N개월 선행 파티션 생성(멱등).
drop_old_partitions    : 보존기간 초과 파티션 DETACH+DROP(콜드 데이터 정리).
스케줄러(worker)가 매일 호출 → 파티션이 항상 준비되고 오래된 것은 정리된다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from gamdap.logging import get_logger

if TYPE_CHECKING:
    from psycopg import Connection

log = get_logger("partitions")

_PARTITIONED = [("core", "price_history"), ("core", "api_call_logs")]


def _month_start(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=UTC)


def _add_month(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = (year * 12 + (month - 1)) + delta
    return idx // 12, idx % 12 + 1


def ensure_month_partitions(conn: Connection, months_ahead: int = 2,
                            now: datetime | None = None) -> list[str]:
    """당월 + months_ahead 선행 월 파티션 생성. 생성/확인된 파티션명 반환(멱등)."""
    now = now or datetime.now(UTC)
    created: list[str] = []
    for schema, table in _PARTITIONED:
        for m in range(months_ahead + 1):
            y, mo = _add_month(now.year, now.month, m)
            start = _month_start(y, mo)
            ey, emo = _add_month(y, mo, 1)
            end = _month_start(ey, emo)
            pname = f"{table}_{start:%Y_%m}"
            # 세이브포인트로 격리: DEFAULT 파티션에 해당 월 데이터가 이미 있으면
            # 그 월 생성은 충돌 → 스킵하고 나머지(미래 월)는 계속 생성.
            conn.execute("SAVEPOINT sp_part")
            try:
                # DDL은 바인드 파라미터 불가 → 내부 생성 날짜를 리터럴로(안전).
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {schema}.{pname} "
                    f"PARTITION OF {schema}.{table} "
                    f"FOR VALUES FROM ('{start:%Y-%m-%d}') TO ('{end:%Y-%m-%d}')"
                )
                conn.execute("RELEASE SAVEPOINT sp_part")
                created.append(pname)
            except Exception as exc:  # noqa: BLE001
                conn.execute("ROLLBACK TO SAVEPOINT sp_part")
                log.warning("partitions.skip", partition=pname, reason=str(exc)[:80])
    log.info("partitions.ensured", count=len(created))
    return created


def drop_old_partitions(conn: Connection, retain_months: int = 12,
                        now: datetime | None = None) -> list[str]:
    """보존기간(개월) 초과 파티션을 DETACH 후 DROP. 정리된 파티션명 반환."""
    now = now or datetime.now(UTC)
    cy, cm = _add_month(now.year, now.month, -retain_months)
    cutoff = _month_start(cy, cm)
    dropped: list[str] = []
    for schema, table in _PARTITIONED:
        rows = conn.execute(
            """
            SELECT c.relname FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            JOIN pg_class p ON p.oid = i.inhparent
            JOIN pg_namespace n ON n.oid = p.relnamespace
            WHERE n.nspname = %s AND p.relname = %s AND c.relname ~ '_\\d{4}_\\d{2}$'
            """,
            (schema, table),
        ).fetchall()
        for r in rows:
            name = r["relname"]
            try:
                ym = name.rsplit("_", 2)[-2:]
                dt = _month_start(int(ym[0]), int(ym[1]))
            except (ValueError, IndexError):
                continue
            if dt < cutoff:
                conn.execute(f"ALTER TABLE {schema}.{table} DETACH PARTITION {schema}.{name}")
                conn.execute(f"DROP TABLE {schema}.{name}")
                dropped.append(name)
    if dropped:
        log.info("partitions.dropped", count=len(dropped), names=dropped)
    return dropped

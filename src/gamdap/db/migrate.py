"""경량 SQL 마이그레이션 러너.

- migrations/*.sql 를 파일명 오름차순으로 적용
- 적용 이력을 public.schema_migrations 에 기록(멱등)
- 각 파일은 단일 트랜잭션으로 실행(부분 적용 방지)

Alembic 대신 투명한 SQL 우선. 필요 시 Alembic으로 승격 가능.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from gamdap.db.pool import transaction
from gamdap.logging import get_logger

log = get_logger("migrate")

# 컨테이너/배포 환경에서 GAMDAP_MIGRATIONS_DIR 로 오버라이드 가능
MIGRATIONS_DIR = Path(
    os.environ.get("GAMDAP_MIGRATIONS_DIR")
    or Path(__file__).resolve().parents[3] / "migrations"
)

_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    filename    TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _discover() -> list[Path]:
    if not MIGRATIONS_DIR.is_dir():
        raise FileNotFoundError(f"migrations 디렉토리 없음: {MIGRATIONS_DIR}")
    return sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def run_migrations() -> int:
    """미적용 마이그레이션을 적용. 적용 건수 반환."""
    files = _discover()
    applied = 0

    with transaction() as conn:
        conn.execute(_BOOTSTRAP)
        rows = conn.execute("SELECT filename, checksum FROM public.schema_migrations").fetchall()
        done = {r["filename"]: r["checksum"] for r in rows}

    for path in files:
        sql = path.read_text(encoding="utf-8")
        cs = _checksum(sql)
        if path.name in done:
            if done[path.name] != cs:
                log.warning("migration.checksum_mismatch", file=path.name,
                            expected=done[path.name], actual=cs)
            continue
        log.info("migration.apply", file=path.name)
        with transaction() as conn:
            conn.execute(sql)
            conn.execute(
                "INSERT INTO public.schema_migrations (filename, checksum) VALUES (%s, %s)",
                (path.name, cs),
            )
        applied += 1

    log.info("migration.done", applied=applied, total=len(files))
    return applied

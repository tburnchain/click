"""psycopg3 연결 풀 + 트랜잭션 컨텍스트."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from gamdap.config import get_settings


@lru_cache
def get_pool() -> ConnectionPool:
    s = get_settings()
    pool = ConnectionPool(
        conninfo=s.db_dsn,
        min_size=s.db_pool_min,
        max_size=s.db_pool_max,
        kwargs={"row_factory": dict_row, "autocommit": False},
        open=True,
    )
    return pool


@contextmanager
def transaction() -> Iterator[Connection]:
    """트랜잭션 스코프. 예외 시 롤백, 정상 종료 시 커밋."""
    pool = get_pool()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

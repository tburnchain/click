"""포인트 원장 — 구독 포인트 지급/차감. 잔액은 스냅샷으로 원장에 기록(감사 추적)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Connection


class InsufficientPoints(Exception):
    def __init__(self, need: int, have: int) -> None:
        super().__init__(f"포인트 부족: 필요 {need}, 보유 {have}")
        self.need, self.have = need, have


def balance(conn: Connection, tenant_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(sum(delta),0) AS b FROM core.point_ledger WHERE tenant_id=%s",
        (tenant_id,),
    ).fetchone()
    return int(row["b"] or 0)


def _record(conn: Connection, tenant_id: int, delta: int, reason: str, ref: str | None) -> int:
    bal = balance(conn, tenant_id) + delta
    conn.execute(
        "INSERT INTO core.point_ledger (tenant_id, delta, balance, reason, ref) "
        "VALUES (%s,%s,%s,%s,%s)",
        (tenant_id, delta, bal, reason, ref),
    )
    return bal


def grant(conn: Connection, tenant_id: int, amount: int, reason: str = "grant",
          ref: str | None = None) -> int:
    """포인트 지급. 새 잔액 반환."""
    return _record(conn, tenant_id, abs(amount), reason, ref)


def spend(conn: Connection, tenant_id: int, amount: int, reason: str = "spend",
          ref: str | None = None) -> int:
    """포인트 차감. 잔액 부족 시 InsufficientPoints. 새 잔액 반환."""
    have = balance(conn, tenant_id)
    if have < amount:
        raise InsufficientPoints(amount, have)
    return _record(conn, tenant_id, -abs(amount), reason, ref)


def ledger(conn: Connection, tenant_id: int, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT delta, balance, reason, ref, created_at FROM core.point_ledger "
        "WHERE tenant_id=%s ORDER BY id DESC LIMIT %s",
        (tenant_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]

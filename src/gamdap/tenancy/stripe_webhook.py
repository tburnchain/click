"""Stripe 웹훅 처리(§19.3) — 서명 검증 + 구독 상태 동기화.

서명 검증은 Stripe 표준 스킴(t=timestamp,v1=hmac_sha256(secret, "t.payload")).
금전 행위는 Stripe UI에서, 시스템은 상태만 반영한다.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from psycopg import Connection

# Stripe 이벤트 → 내부 구독 상태
_STATUS_MAP = {
    "customer.subscription.created": "active",
    "customer.subscription.updated": None,       # data.object.status 사용
    "customer.subscription.deleted": "canceled",
    "invoice.payment_failed": "past_due",
    "invoice.paid": "active",
}


def verify_stripe_signature(payload: str, sig_header: str, secret: str,
                            timestamp: int | None = None, tolerance: int = 300) -> bool:
    """Stripe-Signature 헤더 검증. timestamp 주입 시 허용오차(tolerance) 체크."""
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    t = parts.get("t")
    v1 = parts.get("v1")
    if not t or not v1:
        return False
    signed_payload = f"{t}.{payload}"
    expected = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, v1):
        return False
    if timestamp is not None:
        try:
            if abs(timestamp - int(t)) > tolerance:
                return False
        except ValueError:
            return False
    return True


def apply_stripe_event(event: dict[str, Any]) -> dict | None:
    """Stripe 이벤트 → 구독 업데이트 필드. 무관 이벤트는 None."""
    etype = event.get("type", "")
    if etype not in _STATUS_MAP:
        return None
    obj = (event.get("data") or {}).get("object") or {}
    sub_id = obj.get("id") or obj.get("subscription")
    if not sub_id:
        return None
    status = _STATUS_MAP[etype]
    if status is None:  # updated → 객체 상태 반영
        raw = obj.get("status", "active")
        status = {"active": "active", "trialing": "trialing",
                  "past_due": "past_due", "canceled": "canceled",
                  "unpaid": "past_due"}.get(raw, "active")
    period_end = obj.get("current_period_end")  # epoch seconds (있으면)
    return {"external_sub_id": sub_id, "status": status, "current_period_end_epoch": period_end}


def sync_subscription(conn: Connection, update: dict) -> bool:
    """external_sub_id 기준으로 구독 상태 동기화."""
    from datetime import UTC, datetime

    period_end = None
    if update.get("current_period_end_epoch"):
        period_end = datetime.fromtimestamp(int(update["current_period_end_epoch"]), tz=UTC)
    n = conn.execute(
        "UPDATE core.subscriptions SET status=%s, current_period_end=COALESCE(%s, current_period_end) "
        "WHERE external_sub_id=%s",
        (update["status"], period_end, update["external_sub_id"]),
    ).rowcount
    return n > 0


def parse_event(payload: str) -> dict:
    return json.loads(payload)

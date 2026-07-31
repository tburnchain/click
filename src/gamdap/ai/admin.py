"""AI 제공자 관리(§7.5) — 등록·역량 토글·제안 승인/반려.

승인 게이트: AI 제안은 반드시 여기서 승인되어야 코어에 반영된다(category_mapping 한정 실제 반영).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from gamdap.logging import get_logger

if TYPE_CHECKING:
    from psycopg import Connection

log = get_logger("ai.admin")


def register_provider(
    conn: Connection, *, code: str, adapter: str, display_name: str,
    config: dict | None = None, monthly_budget_usd: float | None = None,
    secret_ref: str | None = None, is_enabled: bool = False,
) -> int:
    """제공자 등록(기본 비활성). 헬스체크 후 관리자가 역량 토글로 활성화."""
    row = conn.execute(
        "INSERT INTO core.ai_providers "
        "(code, display_name, adapter, secret_ref, is_enabled, monthly_budget_usd, config) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (code) DO UPDATE SET adapter=EXCLUDED.adapter, "
        "display_name=EXCLUDED.display_name, config=EXCLUDED.config, "
        "monthly_budget_usd=EXCLUDED.monthly_budget_usd, updated_at=now() "
        "RETURNING id",
        (code, display_name, adapter, secret_ref, is_enabled, monthly_budget_usd,
         json.dumps(config or {}, ensure_ascii=False)),
    ).fetchone()
    return int(row["id"])


def set_provider_enabled(conn: Connection, provider_id: int, enabled: bool) -> None:
    conn.execute("UPDATE core.ai_providers SET is_enabled=%s, updated_at=now() WHERE id=%s",
                 (enabled, provider_id))


def set_capability(conn: Connection, provider_id: int, capability: str,
                   *, enabled: bool = True, priority: int = 100) -> None:
    conn.execute(
        "INSERT INTO core.ai_capabilities (provider_id, capability, is_enabled, priority) "
        "VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (provider_id, capability) DO UPDATE SET "
        "is_enabled=EXCLUDED.is_enabled, priority=EXCLUDED.priority",
        (provider_id, capability, enabled, priority),
    )


def accept_suggestion(conn: Connection, suggestion_id: int, reviewer: int | None = None) -> bool:
    """제안 승인 + 안전 반영. category_mapping 만 코어에 실제 적용(나머지는 상태만 승인)."""
    s = conn.execute(
        "SELECT id, capability, target_type, target_id, suggestion "
        "FROM core.ai_suggestions WHERE id=%s AND status='pending'",
        (suggestion_id,),
    ).fetchone()
    if s is None:
        return False

    applied = False
    if s["capability"] == "category_mapping" and s["target_type"] == "network_category":
        data = s["suggestion"] if isinstance(s["suggestion"], dict) else json.loads(s["suggestion"])
        slug = data.get("slug")
        if slug and s["target_id"]:
            # target_id = "network_id:raw_name"
            net_str, _, raw_name = str(s["target_id"]).partition(":")
            cat = conn.execute("SELECT id FROM core.categories WHERE slug=%s", (slug,)).fetchone()
            if cat is not None:
                conn.execute(
                    "UPDATE core.network_categories SET category_id=%s, mapped_by='human' "
                    "WHERE network_id=%s AND raw_name=%s",
                    (cat["id"], int(net_str), raw_name),
                )
                applied = True

    conn.execute(
        "UPDATE core.ai_suggestions SET status='accepted', reviewed_by=%s, reviewed_at=now() "
        "WHERE id=%s", (reviewer, suggestion_id),
    )
    log.info("ai.suggestion_accepted", id=suggestion_id, applied=applied)
    return True


def reject_suggestion(conn: Connection, suggestion_id: int, reviewer: int | None = None) -> bool:
    n = conn.execute(
        "UPDATE core.ai_suggestions SET status='rejected', reviewed_by=%s, reviewed_at=now() "
        "WHERE id=%s AND status='pending'", (reviewer, suggestion_id),
    ).rowcount
    return n > 0

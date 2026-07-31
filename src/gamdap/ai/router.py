"""Capability Router(§7.3) — 역량별 제공자 라우팅·폴백·예산 가드·제안 격리.

가드레일:
  - AI는 T1(가격/재고/수수료)을 절대 수정 못 함. 산출은 ai_suggestions(pending)로만.
  - 제공자별 월 예산 초과 시 스킵(자동 비활성 효과).
  - 모든 호출은 api_call_logs 에 비용·지연 기록.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from gamdap.ai.registry import build_adapter
from gamdap.logging import get_logger

if TYPE_CHECKING:
    from psycopg import Connection

log = get_logger("ai.router")


def within_budget(spent_usd: float, monthly_budget_usd: float | None) -> bool:
    """예산 가드(순수). budget None=무제한."""
    if monthly_budget_usd is None:
        return True
    return spent_usd < monthly_budget_usd


def _month_spend(conn: Connection, provider: str) -> float:
    row = conn.execute(
        "SELECT COALESCE(sum(cost_usd),0) AS s FROM core.api_call_logs "
        "WHERE provider = %s AND kind = 'ai_assist' "
        "AND called_at >= date_trunc('month', now())",
        (provider,),
    ).fetchone()
    return float(row["s"] or 0)


def route_capability(
    conn: Connection, capability: str, payload: dict,
    *, target_type: str | None = None, target_id: str | None = None,
    auto_apply: bool = False,
) -> dict | None:
    """역량을 우선순위대로 라우팅. 성공 시 {suggestion_id, data, confidence, provider} 반환.

    활성 제공자가 없으면 None → 호출자는 코어 규칙만으로 진행(정상).
    """
    caps = conn.execute(
        """
        SELECT ac.provider_id, ac.priority, p.code, p.adapter, p.config, p.monthly_budget_usd
        FROM core.ai_capabilities ac
        JOIN core.ai_providers p ON p.id = ac.provider_id
        WHERE ac.capability = %s AND ac.is_enabled AND p.is_enabled
        ORDER BY ac.priority ASC
        """,
        (capability,),
    ).fetchall()

    for cap in caps:
        provider_code = cap["code"]
        budget = float(cap["monthly_budget_usd"]) if cap["monthly_budget_usd"] is not None else None
        spent = _month_spend(conn, provider_code)
        if not within_budget(spent, budget):
            log.warning("ai.budget_exceeded", provider=provider_code, spent=spent, budget=budget)
            continue

        try:
            adapter = build_adapter(cap["adapter"], cap["config"] or {})
        except KeyError:
            log.warning("ai.adapter_missing", adapter=cap["adapter"])
            continue

        health = adapter.health()
        if not health.ok:
            log.warning("ai.adapter_unhealthy", provider=provider_code, detail=health.detail)
            continue

        started = datetime.now(UTC)
        suggestion = adapter.run(capability, payload)
        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        cost = adapter.unit_cost()

        conn.execute(
            "INSERT INTO core.api_call_logs "
            "(provider, kind, capability, request, http_status, latency_ms, cost_usd, called_at) "
            "VALUES (%s,'ai_assist',%s,%s,200,%s,%s,%s)",
            (provider_code, capability, json.dumps(payload, ensure_ascii=False, default=str),
             latency_ms, cost, started),
        )

        status = "auto_applied" if auto_apply else "pending"
        row = conn.execute(
            "INSERT INTO core.ai_suggestions "
            "(provider_id, capability, target_type, target_id, suggestion, confidence, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (cap["provider_id"], capability, target_type, target_id,
             json.dumps(suggestion.data, ensure_ascii=False, default=str),
             suggestion.confidence, status),
        ).fetchone()

        return {
            "suggestion_id": int(row["id"]),
            "data": suggestion.data,
            "confidence": suggestion.confidence,
            "provider": provider_code,
            "status": status,
        }

    return None

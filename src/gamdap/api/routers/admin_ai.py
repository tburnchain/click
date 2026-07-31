"""AI 제공자·제안 관리 API(§9.1 admin). admin 권한 전용(M11 엔타이틀먼트로 보호)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gamdap.ai import admin as ai_admin
from gamdap.db import transaction

router = APIRouter(prefix="/api/v1/ai", tags=["ai-admin"])


class ProviderIn(BaseModel):
    code: str
    adapter: str
    display_name: str
    config: dict = {}
    monthly_budget_usd: float | None = None
    secret_ref: str | None = None
    is_enabled: bool = False


class CapabilityIn(BaseModel):
    capability: str
    enabled: bool = True
    priority: int = 100


class EnableIn(BaseModel):
    is_enabled: bool


@router.get("/providers")
def list_providers() -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            "SELECT p.id, p.code, p.display_name, p.adapter, p.is_enabled, p.monthly_budget_usd, "
            "COALESCE(json_agg(json_build_object('capability', ac.capability, "
            "'enabled', ac.is_enabled, 'priority', ac.priority)) "
            "FILTER (WHERE ac.id IS NOT NULL), '[]') AS capabilities "
            "FROM core.ai_providers p "
            "LEFT JOIN core.ai_capabilities ac ON ac.provider_id = p.id "
            "GROUP BY p.id ORDER BY p.id"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/providers")
def create_provider(body: ProviderIn) -> dict:
    with transaction() as conn:
        pid = ai_admin.register_provider(
            conn, code=body.code, adapter=body.adapter, display_name=body.display_name,
            config=body.config, monthly_budget_usd=body.monthly_budget_usd,
            secret_ref=body.secret_ref, is_enabled=body.is_enabled,
        )
    return {"id": pid}


@router.patch("/providers/{provider_id}")
def toggle_provider(provider_id: int, body: EnableIn) -> dict:
    with transaction() as conn:
        ai_admin.set_provider_enabled(conn, provider_id, body.is_enabled)
    return {"id": provider_id, "is_enabled": body.is_enabled}


@router.post("/providers/{provider_id}/capabilities")
def set_capability(provider_id: int, body: CapabilityIn) -> dict:
    with transaction() as conn:
        ai_admin.set_capability(conn, provider_id, body.capability,
                                enabled=body.enabled, priority=body.priority)
    return {"provider_id": provider_id, "capability": body.capability, "enabled": body.enabled}


@router.get("/suggestions")
def list_suggestions(status: str = "pending", limit: int = 100) -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, provider_id, capability, target_type, target_id, suggestion, "
            "confidence, status, created_at FROM core.ai_suggestions "
            "WHERE status = %s ORDER BY created_at DESC LIMIT %s",
            (status, min(limit, 500)),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/suggestions/{suggestion_id}/accept")
def accept(suggestion_id: int) -> dict:
    with transaction() as conn:
        ok = ai_admin.accept_suggestion(conn, suggestion_id)
    if not ok:
        raise HTTPException(404, "suggestion not found or not pending")
    return {"id": suggestion_id, "status": "accepted"}


@router.post("/suggestions/{suggestion_id}/reject")
def reject(suggestion_id: int) -> dict:
    with transaction() as conn:
        ok = ai_admin.reject_suggestion(conn, suggestion_id)
    if not ok:
        raise HTTPException(404, "suggestion not found or not pending")
    return {"id": suggestion_id, "status": "rejected"}

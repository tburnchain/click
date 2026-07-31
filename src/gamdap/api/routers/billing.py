"""SaaS 엔타이틀먼트 게이트 + Stripe 웹훅(§19)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from gamdap.config import get_settings
from gamdap.db import transaction
from gamdap.tenancy.entitlements import TenantContext, feature_enabled, resolve_context
from gamdap.tenancy.stripe_webhook import (
    apply_stripe_event,
    parse_event,
    sync_subscription,
    verify_stripe_signature,
)

router = APIRouter(prefix="/api/v1", tags=["billing"])


def get_tenant_context(x_api_key: str | None = Header(default=None)) -> TenantContext | None:
    """API 키 → 테넌트 컨텍스트. 키 없으면 None(require_api_key=False 시 공개 접근 허용)."""
    settings = get_settings()
    if not x_api_key:
        if settings.require_api_key:
            raise HTTPException(401, "X-Api-Key 필요")
        return None
    with transaction() as conn:
        ctx = resolve_context(conn, x_api_key)
    if ctx is None and settings.require_api_key:
        raise HTTPException(401, "유효하지 않은 API 키")
    return ctx


def require_feature(feature: str):
    """플랜 기능 게이트 의존성 팩토리. 예: Depends(require_feature('advanced_analytics'))."""
    def _dep(ctx: TenantContext | None = Depends(get_tenant_context)) -> TenantContext | None:
        settings = get_settings()
        if ctx is None:
            if settings.require_api_key:
                raise HTTPException(401, "인증 필요")
            return None  # 공개 모드
        if not feature_enabled(ctx.entitlements, feature):
            raise HTTPException(402, f"'{feature}' 은(는) 현재 플랜({ctx.plan_code})에 포함되지 않습니다")
        return ctx
    return _dep


@router.get("/me/entitlements")
def my_entitlements(ctx: TenantContext | None = Depends(get_tenant_context)) -> dict:
    if ctx is None:
        return {"plan": "public", "entitlements": {}}
    return {"plan": ctx.plan_code, "tenant_id": ctx.tenant_id, "entitlements": ctx.entitlements}


@router.post("/billing/stripe/webhook")
async def stripe_webhook(request: Request,
                         stripe_signature: str | None = Header(default=None)) -> dict:
    settings = get_settings()
    payload = (await request.body()).decode("utf-8")

    if settings.stripe_webhook_secret and (
        not stripe_signature
        or not verify_stripe_signature(payload, stripe_signature, settings.stripe_webhook_secret)
    ):
        raise HTTPException(400, "서명 검증 실패")

    event = parse_event(payload)
    update = apply_stripe_event(event)
    if update is None:
        return {"handled": False, "reason": "ignored_event_type"}
    with transaction() as conn:
        synced = sync_subscription(conn, update)
    return {"handled": True, "synced": synced, "status": update["status"]}

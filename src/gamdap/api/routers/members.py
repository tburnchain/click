"""회원 SaaS API — 인증·포인트·제휴계정·빌더·공개 사이트 렌더."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from gamdap.db import transaction
from gamdap.members import network_catalog, points, service
from gamdap.members.points import InsufficientPoints

router = APIRouter(prefix="/api/v1", tags=["members"])


# ── 인증 의존성 ──
def require_member(authorization: str | None = Header(default=None),
                   x_member_token: str | None = Header(default=None)) -> dict:
    token = x_member_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(401, "로그인이 필요합니다")
    with transaction() as conn:
        m = service.authenticate(conn, token)
    if m is None:
        raise HTTPException(401, "세션이 유효하지 않습니다")
    return m


# ── 요청 스키마 ──
class SignupIn(BaseModel):
    email: str
    password: str = Field(min_length=6)
    display_name: str | None = None
    plan: str = "free"          # 회원가입은 무료. 유료는 가입 후 /me/subscribe.
    ref: str | None = None


class SubscribeIn(BaseModel):
    plan: str


class LoginIn(BaseModel):
    email: str
    password: str


class AffiliateIn(BaseModel):
    network_code: str
    tracking: dict
    secret: str | None = None


class ClaimIn(BaseModel):
    template_code: str
    title: str
    affiliate_network_code: str | None = None
    filter: dict = {}
    owner_info: dict = {}


# ── 공개(랜딩·가입) ──
@router.get("/affiliate-networks")
def affiliate_networks() -> dict:
    """글로벌 제휴 네트워크 카탈로그 + 데이터 추출 요구사항(가입만/API/피드/수동 · 자격증명 미포함)."""
    return {"networks": network_catalog.list_networks(),
            "keyless_sources": network_catalog.KEYLESS_SOURCES,
            "common_cautions": network_catalog.COMMON_CAUTIONS,
            "summary": network_catalog.catalog_summary(),
            "extraction_summary": network_catalog.extraction_summary()}


@router.get("/plans")
def plans() -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            "SELECT code, display_name, price_monthly_usd, tier, monthly_points, entitlements "
            "FROM core.plans WHERE tier IS NOT NULL ORDER BY price_monthly_usd"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/auth/signup")
def signup(body: SignupIn) -> dict:
    try:
        with transaction() as conn:
            return service.signup(conn, str(body.email), body.password, body.display_name,
                                  body.plan, body.ref)
    except service.AuthError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/auth/login")
def login(body: LoginIn) -> dict:
    try:
        with transaction() as conn:
            return service.login(conn, str(body.email), body.password)
    except service.AuthError as e:
        raise HTTPException(401, str(e)) from e


# ── 회원 전용 ──
@router.get("/me")
def me(m: dict = Depends(require_member)) -> dict:
    return {"email": m["email"], "display_name": m.get("display_name"),
            "plan": m.get("plan_code") or "free",
            "tier": m.get("tier") or m.get("plan_code") or "free",
            "points": m["points"],
            "referral_code": m.get("referral_code"),
            "referral_count": m.get("referral_count", 0),
            "referral_points": m.get("referral_points", 0)}


@router.post("/me/subscribe")
def subscribe(body: SubscribeIn, m: dict = Depends(require_member)) -> dict:
    try:
        with transaction() as conn:
            return service.subscribe(conn, m["tenant_id"], body.plan)
    except service.BuilderError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/me/points")
def my_points(m: dict = Depends(require_member)) -> dict:
    with transaction() as conn:
        return {"balance": points.balance(conn, m["tenant_id"]),
                "ledger": points.ledger(conn, m["tenant_id"])}


@router.get("/me/affiliate-accounts")
def my_affiliates(m: dict = Depends(require_member)) -> list[dict]:
    with transaction() as conn:
        return service.list_affiliate_accounts(conn, m["tenant_id"])


@router.post("/me/affiliate-accounts")
def connect_affiliate(body: AffiliateIn, m: dict = Depends(require_member)) -> dict:
    try:
        with transaction() as conn:
            aid = service.connect_affiliate(conn, m["tenant_id"], body.network_code,
                                            body.tracking, body.secret)
        return {"account_id": aid, "network": body.network_code}
    except service.BuilderError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/builders")
def builders() -> list[dict]:
    with transaction() as conn:
        return service.list_builders(conn)


@router.get("/showcase")
def showcase() -> list[dict]:
    with transaction() as conn:
        return service.showcase(conn)


@router.post("/builders/claim")
def claim(body: ClaimIn, m: dict = Depends(require_member)) -> dict:
    try:
        with transaction() as conn:
            return service.claim_builder(conn, m["tenant_id"], body.template_code, body.title,
                                         body.affiliate_network_code, body.filter, body.owner_info)
    except InsufficientPoints as e:
        raise HTTPException(402, str(e)) from e
    except service.BuilderError as e:
        raise HTTPException(400, str(e)) from e


class SiteUpdateIn(BaseModel):
    title: str | None = None
    owner_info: dict | None = None
    filter: dict | None = None
    config: dict | None = None
    status: str | None = None


@router.get("/me/sites")
def my_sites(m: dict = Depends(require_member)) -> list[dict]:
    with transaction() as conn:
        return service.list_sites(conn, m["tenant_id"])


@router.get("/me/sites/{site_id}")
def get_site(site_id: int, m: dict = Depends(require_member)) -> dict:
    with transaction() as conn:
        s = service.get_site(conn, m["tenant_id"], site_id)
    if s is None:
        raise HTTPException(404, "사이트를 찾을 수 없습니다")
    return s


@router.get("/me/sites/{site_id}/export")
def export_site(site_id: int, request: Request, site_url: str | None = None,
                m: dict = Depends(require_member)) -> dict:
    """구매한 사이트의 SEO·AI검색 최적화 HTML 코드 공개(소유자 전용, 미리보기)."""
    base = str(request.base_url).rstrip("/")
    try:
        with transaction() as conn:
            return service.export_site(conn, m["tenant_id"], site_id, base_url=base,
                                       site_url=site_url or None)
    except service.BuilderError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/me/sites/{site_id}/export.zip")
def export_zip(site_id: int, request: Request, site_url: str | None = None,
               m: dict = Depends(require_member)) -> Response:
    """다중 페이지(상품 상세 포함) 배포 번들 zip 다운로드(소유자 전용)."""
    base = str(request.base_url).rstrip("/")
    try:
        with transaction() as conn:
            _fn, blob, count = service.export_zip(conn, m["tenant_id"], site_id,
                                                  base_url=base, site_url=site_url or None)
    except service.BuilderError as e:
        raise HTTPException(404, str(e)) from e
    return Response(
        content=blob, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="gamdap-site-{site_id}.zip"',
                 "X-File-Count": str(count)},
    )


@router.patch("/me/sites/{site_id}")
def update_site(site_id: int, body: SiteUpdateIn, m: dict = Depends(require_member)) -> dict:
    try:
        with transaction() as conn:
            s = service.update_site(conn, m["tenant_id"], site_id, title=body.title,
                                    owner_info=body.owner_info, filter=body.filter,
                                    config=body.config, status=body.status)
        return s or {}
    except service.BuilderError as e:
        raise HTTPException(404, str(e)) from e


# ── 공개 사이트 렌더 ──
@router.get("/site/{slug}")
def public_site(slug: str, sort: str = "score") -> dict:
    with transaction() as conn:
        data = service.render_site(conn, slug, sort=sort)
    if data is None:
        raise HTTPException(404, "사이트를 찾을 수 없습니다")
    return data


@router.get("/site/{slug}/product/{offer_id}")
def public_product(slug: str, offer_id: int) -> dict:
    with transaction() as conn:
        data = service.render_product(conn, slug, offer_id)
    if data is None:
        raise HTTPException(404, "상품을 찾을 수 없습니다")
    return data

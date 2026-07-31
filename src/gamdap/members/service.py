"""회원 서비스 — 가입/로그인·제휴계정 연결·빌더 클레임·사이트 렌더링."""

from __future__ import annotations

import json
import re
import secrets
from typing import TYPE_CHECKING, Any

from gamdap.members import points
from gamdap.members.affiliate import apply_affiliate
from gamdap.members.security import (
    encrypt,
    hash_password,
    new_token,
    token_hash,
    verify_password,
)

if TYPE_CHECKING:
    from psycopg import Connection


class AuthError(Exception):
    pass


class BuilderError(Exception):
    pass


def _slugify(text: str) -> str:
    s = re.sub(r"[^0-9a-z가-힣]+", "-", (text or "").lower()).strip("-")
    return (s or "site")[:40] + "-" + secrets.token_hex(3)


# 리퍼럴(추천 가입) 커미션 — 등급별 지급 포인트
_REFERRAL_REWARD = {"basic": 50, "pro": 100, "premium": 200, "vip": 300}


def _gen_referral_code() -> str:
    return secrets.token_hex(4).upper()


# ── 인증 ──
def signup(conn: Connection, email: str, password: str, display_name: str | None = None,
           plan_code: str = "free", ref: str | None = None) -> dict:
    # 회원가입은 누구나 무료(free). 유료 등급은 가입 후 구독(subscribe)에서 선택.
    exists = conn.execute("SELECT 1 FROM core.users WHERE email=%s", (email,)).fetchone()
    if exists:
        raise AuthError("이미 가입된 이메일입니다")
    plan = conn.execute(
        "SELECT code, monthly_points, tier FROM core.plans WHERE code=%s AND (tier IS NOT NULL OR code='free')",
        (plan_code,),
    ).fetchone()
    if plan is None:
        raise AuthError("유효하지 않은 등급")

    # 추천인 확인(유효한 추천코드일 때만)
    referrer = None
    if ref:
        referrer = conn.execute(
            "SELECT id FROM core.tenants WHERE referral_code=%s AND status='active'",
            (ref.strip().upper(),),
        ).fetchone()

    tid = conn.execute(
        "INSERT INTO core.tenants (name, owner_email, referral_code, referred_by) "
        "VALUES (%s,%s,%s,%s) RETURNING id",
        (display_name or email.split("@")[0], email, _gen_referral_code(),
         referrer["id"] if referrer else None),
    ).fetchone()["id"]
    uid = conn.execute(
        "INSERT INTO core.users (tenant_id, email, role, password_hash, display_name) "
        "VALUES (%s,%s,'owner',%s,%s) RETURNING id",
        (tid, email, hash_password(password), display_name),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO core.subscriptions (tenant_id, plan_code, status) VALUES (%s,%s,'active')",
        (tid, plan_code),
    )
    points.grant(conn, tid, int(plan["monthly_points"]), reason="signup_grant", ref=plan_code)

    # 추천 커미션은 추천된 회원이 '유료 구독'할 때 지급(무료가입은 referred_by만 기록,
    # 이후 subscribe()에서 1회 정산). 유료로 직접 가입하는 경우엔 즉시 지급.
    if referrer and referrer["id"] != tid and plan["tier"] is not None:
        reward = _REFERRAL_REWARD.get(plan["tier"], 50)
        conn.execute(
            "INSERT INTO core.referrals (referrer_tenant_id, referred_tenant_id, plan_code, reward_points) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT (referred_tenant_id) DO NOTHING",
            (referrer["id"], tid, plan_code, reward),
        )
        points.grant(conn, referrer["id"], reward, reason="referral_bonus", ref=email)

    token = new_token()
    conn.execute("INSERT INTO core.api_keys (tenant_id, key_hash, label) VALUES (%s,%s,'session')",
                 (tid, token_hash(token)))
    return {"token": token, "tenant_id": tid, "user_id": uid, "plan": plan_code,
            "referred": bool(referrer)}


def subscribe(conn: Connection, tenant_id: int, plan_code: str) -> dict:
    """유료 등급 구독(빌더 만들기 진입점). 월 포인트 지급 + 추천 커미션 1회 정산."""
    plan = conn.execute(
        "SELECT code, monthly_points, tier FROM core.plans WHERE code=%s AND tier IS NOT NULL",
        (plan_code,),
    ).fetchone()
    if plan is None:
        raise BuilderError("유효하지 않은 구독 등급")
    row = conn.execute(
        "SELECT id FROM core.subscriptions WHERE tenant_id=%s AND status IN ('active','trialing') "
        "ORDER BY id DESC LIMIT 1", (tenant_id,),
    ).fetchone()
    if row:
        conn.execute("UPDATE core.subscriptions SET plan_code=%s, status='active' WHERE id=%s",
                     (plan_code, row["id"]))
    else:
        conn.execute("INSERT INTO core.subscriptions (tenant_id, plan_code, status) "
                     "VALUES (%s,%s,'active')", (tenant_id, plan_code))
    points.grant(conn, tenant_id, int(plan["monthly_points"]), reason="subscription_grant", ref=plan_code)

    # 추천 커미션: 추천된 회원이 처음 유료 구독할 때 추천인에게 1회 지급
    t = conn.execute("SELECT referred_by FROM core.tenants WHERE id=%s", (tenant_id,)).fetchone()
    if t and t["referred_by"] and t["referred_by"] != tenant_id:
        reward = _REFERRAL_REWARD.get(plan["tier"], 50)
        ins = conn.execute(
            "INSERT INTO core.referrals (referrer_tenant_id, referred_tenant_id, plan_code, reward_points) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT (referred_tenant_id) DO NOTHING RETURNING id",
            (t["referred_by"], tenant_id, plan_code, reward),
        ).fetchone()
        if ins:
            points.grant(conn, t["referred_by"], reward, reason="referral_bonus", ref=plan_code)

    return {"plan": plan_code, "tier": plan["tier"], "points": points.balance(conn, tenant_id)}


def login(conn: Connection, email: str, password: str) -> dict:
    u = conn.execute(
        "SELECT id, tenant_id, password_hash FROM core.users WHERE email=%s", (email,)
    ).fetchone()
    if u is None or not verify_password(password, u["password_hash"] or ""):
        raise AuthError("이메일 또는 비밀번호가 올바르지 않습니다")
    token = new_token()
    conn.execute("INSERT INTO core.api_keys (tenant_id, key_hash, label) VALUES (%s,%s,'session')",
                 (u["tenant_id"], token_hash(token)))
    return {"token": token, "tenant_id": u["tenant_id"], "user_id": u["id"]}


def authenticate(conn: Connection, token: str) -> dict | None:
    row = conn.execute(
        """
        SELECT t.id AS tenant_id, u.id AS user_id, u.email, u.display_name, t.referral_code,
               s.plan_code, p.tier, p.monthly_points, p.entitlements
        FROM core.api_keys k
        JOIN core.tenants t ON t.id=k.tenant_id AND t.status='active'
        JOIN core.users u ON u.tenant_id=t.id
        LEFT JOIN core.subscriptions s ON s.tenant_id=t.id AND s.status IN ('active','trialing')
        LEFT JOIN core.plans p ON p.code=s.plan_code
        WHERE k.key_hash=%s AND k.is_active
        ORDER BY u.id LIMIT 1
        """,
        (token_hash(token),),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["points"] = points.balance(conn, d["tenant_id"])
    stat = conn.execute(
        "SELECT count(*) AS n, COALESCE(sum(reward_points),0) AS pts "
        "FROM core.referrals WHERE referrer_tenant_id=%s", (d["tenant_id"],),
    ).fetchone()
    d["referral_count"] = int(stat["n"])
    d["referral_points"] = int(stat["pts"])
    return d


# ── 제휴 계정 연결 ──
def connect_affiliate(conn: Connection, tenant_id: int, network_code: str,
                      tracking: dict, secret: str | None = None) -> int:
    net = conn.execute("SELECT id FROM core.networks WHERE code=%s", (network_code,)).fetchone()
    if net is None:
        raise BuilderError(f"네트워크 없음: {network_code}")
    row = conn.execute(
        "INSERT INTO core.member_affiliate_accounts (tenant_id, network_id, tracking, secret_enc) "
        "VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (tenant_id, network_id) DO UPDATE SET tracking=EXCLUDED.tracking, "
        "secret_enc=EXCLUDED.secret_enc, status='active' RETURNING id",
        (tenant_id, net["id"], json.dumps(tracking, ensure_ascii=False),
         encrypt(secret) if secret else None),
    ).fetchone()
    return int(row["id"])


def list_affiliate_accounts(conn: Connection, tenant_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT a.id, n.code AS network_code, n.display_name AS network_name, a.tracking, "
        "(a.secret_enc IS NOT NULL) AS has_secret, a.status "
        "FROM core.member_affiliate_accounts a JOIN core.networks n ON n.id=a.network_id "
        "WHERE a.tenant_id=%s ORDER BY a.id",
        (tenant_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── 빌더 ──
def list_builders(conn: Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, code, name, kind, point_cost, complexity, description, config "
        "FROM core.builder_templates WHERE is_active ORDER BY point_cost",
    ).fetchall()
    return [dict(r) for r in rows]


def claim_builder(conn: Connection, tenant_id: int, template_code: str, title: str,
                  affiliate_network_code: str | None = None, filter: dict | None = None,
                  owner_info: dict | None = None) -> dict:
    from gamdap.members import seo_unique

    tpl = conn.execute(
        "SELECT id, point_cost, name, kind FROM core.builder_templates WHERE code=%s AND is_active",
        (template_code,),
    ).fetchone()
    if tpl is None:
        raise BuilderError("빌더 템플릿 없음")

    # 플랜 max_sites 확인
    ent = conn.execute(
        "SELECT p.entitlements FROM core.subscriptions s JOIN core.plans p ON p.code=s.plan_code "
        "WHERE s.tenant_id=%s AND s.status IN ('active','trialing') LIMIT 1", (tenant_id,)
    ).fetchone()
    max_sites = (ent["entitlements"] if ent else {}).get("max_sites", 1)
    cur = conn.execute("SELECT count(*) AS c FROM core.member_sites WHERE tenant_id=%s",
                       (tenant_id,)).fetchone()["c"]
    if max_sites not in (-1, "*") and cur >= int(max_sites):
        raise BuilderError(f"플랜 사이트 한도 초과 (max {max_sites})")

    # 제휴 계정 바인딩(선택)
    aff_id = None
    if affiliate_network_code:
        a = conn.execute(
            "SELECT a.id FROM core.member_affiliate_accounts a JOIN core.networks n ON n.id=a.network_id "
            "WHERE a.tenant_id=%s AND n.code=%s", (tenant_id, affiliate_network_code)
        ).fetchone()
        aff_id = a["id"] if a else None

    # 포인트 차감(부족 시 InsufficientPoints)
    new_balance = points.spend(conn, tenant_id, int(tpl["point_cost"]),
                               reason="builder_claim", ref=template_code)
    slug = _slugify(title)
    # 생성 시점에 사이트별 독창적 SEO 자동 생성(중복 콘텐츠 회피). slug의 랜덤해시가 시드.
    seo_cfg = seo_unique.generate_profile(slug, title, tpl["kind"])
    site = conn.execute(
        "INSERT INTO core.member_sites (tenant_id, template_id, affiliate_account_id, slug, title, "
        "owner_info, filter, config, points_spent) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "RETURNING id, slug",
        (tenant_id, tpl["id"], aff_id, slug, title,
         json.dumps(owner_info or {}, ensure_ascii=False),
         json.dumps(filter or {}, ensure_ascii=False),
         json.dumps(seo_cfg, ensure_ascii=False), int(tpl["point_cost"])),
    ).fetchone()
    return {"site_id": site["id"], "slug": site["slug"], "points_spent": int(tpl["point_cost"]),
            "balance": new_balance}


_SHOWCASE_ORDER = {
    "shopping": 0, "deal": 1, "ranking": 2, "boutique": 3, "search": 4,
    "directory": 5, "coupon": 6, "blog": 7, "article": 8, "enterprise": 9,
    "general": 10, "mixed": 11,
}


def showcase(conn: Connection) -> list[dict]:
    """랜딩용 대표 빌더 사이트 — 종류별 최신 활성 사이트(미리보기 리스팅, 10 스타일)."""
    rows = conn.execute(
        """
        SELECT DISTINCT ON (t.kind) t.kind, s.slug, s.title, t.name AS builder_name
        FROM core.member_sites s JOIN core.builder_templates t ON t.id = s.template_id
        WHERE s.status='active' AND t.kind = ANY(%s)
        ORDER BY t.kind, s.id DESC
        """,
        (list(_SHOWCASE_ORDER.keys()),),
    ).fetchall()
    return sorted([dict(r) for r in rows], key=lambda r: _SHOWCASE_ORDER.get(r["kind"], 99))


def list_sites(conn: Connection, tenant_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT s.id, s.slug, s.title, s.status, s.views, s.clicks, s.points_spent, s.created_at, "
        "t.name AS builder_name, t.kind FROM core.member_sites s "
        "JOIN core.builder_templates t ON t.id=s.template_id "
        "WHERE s.tenant_id=%s ORDER BY s.id DESC", (tenant_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_site(conn: Connection, tenant_id: int, site_id: int) -> dict | None:
    """편집용 단일 사이트(소유자 전용)."""
    row = conn.execute(
        "SELECT s.id, s.slug, s.title, s.owner_info, s.filter, s.config, s.status, "
        "t.kind, t.name AS builder_name FROM core.member_sites s "
        "JOIN core.builder_templates t ON t.id=s.template_id "
        "WHERE s.id=%s AND s.tenant_id=%s", (site_id, tenant_id)
    ).fetchone()
    return dict(row) if row else None


def update_site(conn: Connection, tenant_id: int, site_id: int, *,
                title: str | None = None, owner_info: dict | None = None,
                filter: dict | None = None, config: dict | None = None,
                status: str | None = None) -> dict | None:
    """사이트 커스터마이즈 저장(소유자 전용). 부분 업데이트."""
    own = conn.execute("SELECT 1 FROM core.member_sites WHERE id=%s AND tenant_id=%s",
                       (site_id, tenant_id)).fetchone()
    if own is None:
        raise BuilderError("사이트를 찾을 수 없습니다")
    sets: list[str] = []
    params: dict = {"id": site_id}
    if title is not None and title.strip():
        sets.append("title=%(title)s")
        params["title"] = title.strip()
    if owner_info is not None:
        sets.append("owner_info=%(owner_info)s")
        params["owner_info"] = json.dumps(owner_info, ensure_ascii=False)
    if filter is not None:
        sets.append("filter=%(filter)s")
        params["filter"] = json.dumps(filter, ensure_ascii=False)
    if config is not None:
        sets.append("config=%(config)s")
        params["config"] = json.dumps(config, ensure_ascii=False)
    if status in ("active", "paused"):
        sets.append("status=%(status)s")
        params["status"] = status
    if sets:
        conn.execute(f"UPDATE core.member_sites SET {', '.join(sets)} WHERE id=%(id)s", params)
    return get_site(conn, tenant_id, site_id)


# ── 사이트 렌더링(공개) ──
_SITE_SORT = {
    "score": "ps.profitability_score DESC NULLS LAST",           # 전체
    "best":  "(o.native_metric_json->>'rating')::float DESC NULLS LAST",  # 베스트(평점순)
    "new":   "o.fetched_at DESC",                                 # 신상품
    "deal":  "COALESCE(o.price_krw, o.price_amount) ASC NULLS LAST",  # 특가(저가순)
}


def render_site(conn: Connection, slug: str, limit: int = 40,
                sort: str = "score", *, track: bool = True,
                require_active: bool = True) -> dict[str, Any] | None:
    status_clause = "AND s.status='active'" if require_active else ""
    site = conn.execute(
        f"""
        SELECT s.id, s.slug, s.title, s.owner_info, s.filter, s.affiliate_account_id,
               s.config AS member_config, s.status,
               t.kind, t.name AS builder_name, t.config,
               n.code AS aff_network, n.tracking_param, a.tracking,
               tn.referral_code AS owner_ref
        FROM core.member_sites s
        JOIN core.builder_templates t ON t.id=s.template_id
        JOIN core.tenants tn ON tn.id=s.tenant_id
        LEFT JOIN core.member_affiliate_accounts a ON a.id=s.affiliate_account_id
        LEFT JOIN core.networks n ON n.id=a.network_id
        WHERE s.slug=%s {status_clause}
        """,
        (slug,),
    ).fetchone()
    if site is None:
        return None

    # 필터로 상품 조회
    f = site["filter"] or {}
    clauses = ["o.is_active"]
    params: dict = {}
    if f.get("network"):
        clauses.append("n.code=%(network)s")
        params["network"] = f["network"]
    if f.get("category"):
        clauses.append("c.slug=%(category)s")
        params["category"] = f["category"]
    if f.get("segment"):
        clauses.append("pc.segment=%(segment)s")
        params["segment"] = f["segment"]
    # 회원이 미리 담아둔 특정 상품 목록
    if f.get("offer_ids"):
        ids = [int(i) for i in f["offer_ids"] if str(i).isdigit()][:200]
        if ids:
            clauses.append("o.id = ANY(%(offer_ids)s)")
            params["offer_ids"] = ids
    where = " AND ".join(clauses)
    order_by = _SITE_SORT.get(sort, _SITE_SORT["score"])
    rows = conn.execute(
        f"""
        SELECT o.id, o.title, o.thumbnail_url, o.landing_url, o.price_krw, o.price_currency,
               o.price_amount, o.network_id, n.code AS net_code, n.display_name AS net_name,
               n.tracking_param AS net_tracking_param, ps.profitability_score, pc.segment,
               (o.native_metric_json->>'brand') AS brand, o.raw_category AS category
        FROM core.offers o JOIN core.networks n ON n.id=o.network_id
        LEFT JOIN core.products p ON p.id=o.product_id
        LEFT JOIN core.categories c ON c.id=p.category_id
        LEFT JOIN analytics.profitability_scores ps ON ps.offer_id=o.id
        LEFT JOIN analytics.product_classifications pc ON pc.offer_id=o.id
        WHERE {where}
        ORDER BY {order_by}, o.id DESC LIMIT %(_lim)s
        """,
        {**params, "_lim": limit},
    ).fetchall()

    # 회원 트래킹 적용 → 딥링크 리라이트
    tracking = site["tracking"] or {}
    products = []
    for r in rows:
        link = apply_affiliate(r["landing_url"], r["net_tracking_param"], tracking)
        products.append({
            "id": r["id"], "title": r["title"], "thumbnail_url": r["thumbnail_url"], "url": link,
            "network": r["net_name"], "price_krw": float(r["price_krw"]) if r["price_krw"] else None,
            "price_amount": float(r["price_amount"]) if r["price_amount"] else None,
            "currency": r["price_currency"], "segment": r["segment"], "brand": r["brand"],
            "category": r["category"],
        })

    if track:
        conn.execute("UPDATE core.member_sites SET views=views+1 WHERE id=%s", (site["id"],))
    return {
        "slug": site["slug"], "title": site["title"], "kind": site["kind"],
        "builder_name": site["builder_name"], "status": site["status"],
        "config": site["config"], "site_config": site["member_config"] or {},
        "owner_info": site["owner_info"] or {},
        "owner_ref": site["owner_ref"],
        "affiliate_applied": bool(tracking), "product_count": len(products), "products": products,
    }


def _owned_site_data(conn: Connection, tenant_id: int, site_id: int):
    """소유자 검증 후 사이트 렌더 데이터 반환. (slug, data)."""
    row = conn.execute(
        "SELECT slug FROM core.member_sites WHERE id=%s AND tenant_id=%s", (site_id, tenant_id),
    ).fetchone()
    if row is None:
        raise BuilderError("사이트를 찾을 수 없습니다")  # 소유자가 아니거나 미구매
    data = render_site(conn, row["slug"], limit=200, track=False, require_active=False)
    if data is None:
        raise BuilderError("사이트 데이터를 불러올 수 없습니다")
    return row["slug"], data


def export_site(conn: Connection, tenant_id: int, site_id: int, *,
                base_url: str = "https://example.com",
                site_url: str | None = None) -> dict[str, Any]:
    """구매(소유)한 사이트를 SEO·AI검색 최적화 정적 HTML로 내보낸다(소유자 전용, 미리보기용)."""
    from gamdap.members import seo_export

    slug, data = _owned_site_data(conn, tenant_id, site_id)
    su = (site_url or base_url).rstrip("/")
    return {
        "slug": slug, "filename": f"{slug}.html", "title": data["title"],
        "product_count": data["product_count"], "total_pages": 1 + data["product_count"],
        "site_url": su,
        "html": seo_export.build_site_html(data, base_url=base_url, slug=slug),
        "robots_txt": seo_export.build_robots(su, slug),
        "sitemap_xml": seo_export.bundle_sitemap(su, [p["id"] for p in data["products"]]),
        "llms_txt": seo_export.build_llms_txt(data, su, slug),
        "seo": seo_export.seo_report(data),
    }


def export_zip(conn: Connection, tenant_id: int, site_id: int, *,
               base_url: str = "https://example.com",
               site_url: str | None = None) -> tuple[str, bytes, int]:
    """다중 페이지 배포 번들(zip) 생성(소유자 전용). (filename, bytes, file_count)."""
    from gamdap.members import seo_export

    slug, data = _owned_site_data(conn, tenant_id, site_id)
    files = seo_export.build_bundle(data, base_url=base_url, slug=slug, site_url=site_url)
    return f"{slug}.zip", seo_export.build_zip(files), len(files)


def render_product(conn: Connection, slug: str, offer_id: int) -> dict[str, Any] | None:
    """상품 상세 — 구매 버튼에 회원 제휴코드가 적용된 딥링크. clicks 증가."""
    site = conn.execute(
        """
        SELECT s.id, s.title AS store, s.owner_info, a.tracking, n.tracking_param,
               tn.referral_code AS owner_ref
        FROM core.member_sites s
        JOIN core.tenants tn ON tn.id = s.tenant_id
        LEFT JOIN core.member_affiliate_accounts a ON a.id = s.affiliate_account_id
        LEFT JOIN core.networks n ON n.id = a.network_id
        WHERE s.slug = %s AND s.status = 'active'
        """,
        (slug,),
    ).fetchone()
    if site is None:
        return None

    o = conn.execute(
        """
        SELECT o.id, o.title, o.thumbnail_url, o.landing_url, o.price_amount, o.price_currency,
               o.price_krw, o.native_metric_json, o.stock_status,
               n.display_name AS net_name, c.name_ko AS category
        FROM core.offers o
        JOIN core.networks n ON n.id = o.network_id
        LEFT JOIN core.products p ON p.id = o.product_id
        LEFT JOIN core.categories c ON c.id = p.category_id
        WHERE o.id = %s
        """,
        (offer_id,),
    ).fetchone()
    if o is None:
        return None

    tracking = site["tracking"] or {}
    buy_url = apply_affiliate(o["landing_url"], site["tracking_param"], tracking)
    conn.execute("UPDATE core.member_sites SET clicks=clicks+1 WHERE id=%s", (site["id"],))

    nm = o["native_metric_json"] or {}
    price = float(o["price_krw"]) if o["price_krw"] else (
        float(o["price_amount"]) if o["price_amount"] else None)
    currency = "KRW" if o["price_krw"] else (o["price_currency"] or "")
    brand = nm.get("brand")
    rating = nm.get("rating")

    # 연관 상품(같은 네트워크 상위 몇 개)
    rel = conn.execute(
        "SELECT o.id, o.title, o.thumbnail_url, o.price_krw, o.price_amount, o.price_currency "
        "FROM core.offers o WHERE o.network_id=(SELECT network_id FROM core.offers WHERE id=%s) "
        "AND o.id<>%s AND o.is_active ORDER BY random() LIMIT 4",
        (offer_id, offer_id),
    ).fetchall()
    related = [
        {"id": r["id"], "title": r["title"], "thumbnail_url": r["thumbnail_url"],
         "price_krw": float(r["price_krw"]) if r["price_krw"] else None,
         "price_amount": float(r["price_amount"]) if r["price_amount"] else None,
         "currency": r["price_currency"]}
        for r in rel
    ]

    return {
        "id": o["id"], "store": site["store"], "owner_info": site["owner_info"] or {},
        "owner_ref": site["owner_ref"],
        "title": o["title"], "brand": brand, "rating": rating, "category": o["category"],
        "price": price, "currency": currency,
        "thumbnail_url": o["thumbnail_url"], "network": o["net_name"],
        "stock_status": o["stock_status"], "buy_url": buy_url,
        "affiliate_applied": bool(tracking), "related": related,
    }

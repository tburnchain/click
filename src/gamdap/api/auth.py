"""관리 API 인증 — API 키 게이트와 스코프 권한.

원칙
  · 키 원문은 저장하지 않는다(sha256 해시만). 발급 시 한 번만 보여준다.
  · 스코프로 최소 권한을 강제한다 — 읽기 키로 정산을 실행할 수 없다.
  · 실패는 이유를 구분하지 않는다(키 없음/틀림/만료 모두 401) — 열거 공격 차단.
  · 파트너 세션은 별도 축이다: 파트너는 '자기 데이터만' 본다.

운영 스위치
  settings.require_api_key 가 False 면 게이트가 열린다(로컬 개발용).
  프로덕션은 반드시 True 여야 하며, 기동 시 경고를 남긴다.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Header, HTTPException

from gamdap.config import get_settings
from gamdap.db import transaction
from gamdap.logging import get_logger
from gamdap.members.security import token_hash

log = get_logger("api.auth")

# 스코프 정의 — admin 은 모든 것을 포함한다
SCOPES = ("growth:read", "growth:write", "growth:settle", "admin")
_KEY_PREFIX = "tbk_"


def gate_enabled() -> bool:
    """관리 API 게이트가 켜져 있는가.

    **프로덕션에서는 설정과 무관하게 항상 켜진다.** require_api_key 를 켜는 것을
    깜빡하는 것만으로 정산 실행 권한이 인터넷에 열리기 때문에, 안전한 쪽이
    기본값이어야 한다. 끄려면 명시적으로 개발/스테이징 환경이어야 한다.
    """
    s = get_settings()
    return s.require_api_key or s.env == "production"


def generate_api_key() -> tuple[str, str, str]:
    """(원문, 해시, 표시용 접두사). 원문은 이 순간에만 존재한다."""
    raw = _KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest(), raw[:12]


def create_api_key(conn, *, tenant_id: int, label: str, scopes: list[str],
                   expires_days: int | None = None) -> dict:
    """API 키 발급. 반환된 원문은 다시 조회할 수 없다."""
    bad = [s for s in scopes if s not in SCOPES]
    if bad:
        raise ValueError(f"알 수 없는 스코프: {', '.join(bad)} (가능: {', '.join(SCOPES)})")
    raw, key_hash, prefix = generate_api_key()
    expires = (datetime.now(UTC) + timedelta(days=expires_days)) if expires_days else None
    row = conn.execute(
        "INSERT INTO core.api_keys (tenant_id, key_hash, label, scopes, expires_at, prefix) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, created_at",
        (tenant_id, key_hash, label, scopes, expires, prefix)).fetchone()
    log.info("api_key.created", key_id=row["id"], tenant=tenant_id, scopes=scopes)
    return {"id": row["id"], "api_key": raw, "prefix": prefix, "scopes": scopes,
            "expires_at": expires, "created_at": row["created_at"],
            "warning": "이 키는 다시 표시되지 않습니다. 지금 안전한 곳에 보관하세요."}


def _lookup(raw_key: str) -> dict | None:
    """키 검증. 만료·비활성은 None(사유를 구분해 알려주지 않는다)."""
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, tenant_id, scopes, expires_at, is_active FROM core.api_keys "
            "WHERE key_hash=%s", (key_hash,)).fetchone()
        if not row or not row["is_active"]:
            return None
        if row["expires_at"] and row["expires_at"] < datetime.now(UTC):
            return None
        conn.execute("UPDATE core.api_keys SET last_used_at=now() WHERE id=%s", (row["id"],))
        return {"key_id": row["id"], "tenant_id": row["tenant_id"],
                "scopes": list(row["scopes"] or [])}


def _extract(authorization: str | None, x_api_key: str | None) -> str | None:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def require_scope(*needed: str):
    """스코프를 요구하는 FastAPI 의존성을 만든다.

    사용: `_=Depends(require_scope("growth:settle"))`
    admin 스코프는 모든 요구를 만족한다.
    """
    def dependency(authorization: str | None = Header(default=None),
                   x_api_key: str | None = Header(default=None)) -> dict:
        if not gate_enabled():
            # 개발 모드에서만 게이트가 열린다. 프로덕션은 아래 gate_enabled() 가 강제한다.
            return {"key_id": None, "tenant_id": None, "scopes": ["admin"], "dev_mode": True}
        raw = _extract(authorization, x_api_key)
        if not raw:
            raise HTTPException(401, "API 키가 필요합니다 (헤더: X-API-Key)")
        ctx = _lookup(raw)
        if not ctx:
            raise HTTPException(401, "유효하지 않은 API 키입니다")
        held = set(ctx["scopes"])
        if "admin" not in held and not set(needed).issubset(held):
            raise HTTPException(
                403, f"권한 부족 — 필요: {', '.join(needed)} / 보유: {', '.join(sorted(held)) or '없음'}")
        return ctx
    return dependency


# ─────────────────────────────────────────────────────────────
# 파트너 세션 — 대시보드 접근(자기 데이터만)
# ─────────────────────────────────────────────────────────────
def issue_partner_session(conn, *, partner_id: int, days: int = 14) -> dict:
    from gamdap.members.security import new_token
    raw = new_token()
    expires = datetime.now(UTC) + timedelta(days=days)
    conn.execute(
        "INSERT INTO core.partner_sessions (partner_id, token_hash, expires_at) "
        "VALUES (%s,%s,%s)", (partner_id, token_hash(raw), expires))
    return {"token": raw, "expires_at": expires}


def authenticate_partner(conn, token: str) -> dict | None:
    row = conn.execute(
        "SELECT s.id, s.partner_id, p.display_name, p.kind, p.tier, p.status "
        "FROM core.partner_sessions s JOIN core.partners p ON p.id=s.partner_id "
        "WHERE s.token_hash=%s AND s.expires_at > now()", (token_hash(token),)).fetchone()
    if not row or row["status"] != "active":
        return None
    conn.execute("UPDATE core.partner_sessions SET last_seen_at=now() WHERE id=%s", (row["id"],))
    return {"partner_id": row["partner_id"], "display_name": row["display_name"],
            "kind": row["kind"], "tier": row["tier"]}


def require_partner(authorization: str | None = Header(default=None),
                    x_partner_token: str | None = Header(default=None)) -> dict:
    """파트너 세션 필수. 자기 데이터 접근에만 쓴다."""
    token = x_partner_token or (
        authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None)
    if not token:
        raise HTTPException(401, "파트너 로그인이 필요합니다")
    with transaction() as conn:
        ctx = authenticate_partner(conn, token.strip())
    if not ctx:
        raise HTTPException(401, "세션이 만료되었거나 유효하지 않습니다")
    return ctx


def assert_own_or_descendant(conn, *, viewer_partner_id: int, target_partner_id: int) -> None:
    """파트너는 자기 자신과 하위 트리만 조회할 수 있다.

    물질화 경로로 판정 — 상위가 하위 실적을 보는 것은 오버라이드 구조상 정당하지만,
    형제나 상위를 보는 것은 정보 유출이다.
    """
    if viewer_partner_id == target_partner_id:
        return
    row = conn.execute(
        "SELECT (SELECT path FROM core.partners WHERE id=%s) LIKE "
        "       (SELECT path FROM core.partners WHERE id=%s) || '%%' AS ok",
        (target_partner_id, viewer_partner_id)).fetchone()
    if not row or not row["ok"]:
        raise HTTPException(403, "조회 권한이 없습니다")

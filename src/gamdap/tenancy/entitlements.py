"""엔타이틀먼트 로직(§19.3) — 플랜별 기능 게이팅·신선도 차등·쿼터.

순수 함수 위주(테스트 가능). DB 연동은 resolve_context 에 격리.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from psycopg import Connection

Entitlements = dict[str, Any]

# 신선도 등급 → 최대 데이터 나이(시간). 하위 플랜은 오래된 스냅샷만.
_FRESHNESS_HOURS = {"hot": 3.0, "12h": 12.0, "daily": 24.0}


def is_unlimited(v: Any) -> bool:
    return v == -1 or v == "*"


def feature_enabled(ent: Entitlements, key: str) -> bool:
    """불리언/문자열 기능 플래그. 'limited' 도 활성으로 취급."""
    v = ent.get(key, False)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() not in ("", "false", "no", "off")
    return bool(v)


def freshness_max_age_hours(ent: Entitlements) -> float:
    """플랜 신선도 등급 → 노출 가능한 데이터 최대 나이(시간)."""
    grade = str(ent.get("freshness", "daily"))
    return _FRESHNESS_HOURS.get(grade, 24.0)


def network_limit_ok(ent: Entitlements, accessed_count: int) -> bool:
    limit = ent.get("networks", 1)
    if is_unlimited(limit):
        return True
    try:
        return accessed_count <= int(limit)
    except (TypeError, ValueError):
        return False


def within_quota(used: int, limit: Any) -> bool:
    """사용량 쿼터. limit -1/'*' 무제한. 0=금지."""
    if is_unlimited(limit):
        return True
    try:
        return used < int(limit)
    except (TypeError, ValueError):
        return False


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


@dataclass
class TenantContext:
    tenant_id: int
    plan_code: str
    entitlements: Entitlements


def resolve_context(conn: Connection, raw_api_key: str) -> TenantContext | None:
    """API 키 → 테넌트 → 활성 구독 → 플랜 엔타이틀먼트 해소."""
    key_hash = hash_api_key(raw_api_key)
    row = conn.execute(
        """
        SELECT t.id AS tenant_id, s.plan_code, p.entitlements
        FROM core.api_keys k
        JOIN core.tenants t ON t.id = k.tenant_id AND t.status = 'active'
        LEFT JOIN core.subscriptions s
               ON s.tenant_id = t.id AND s.status IN ('trialing','active')
        LEFT JOIN core.plans p ON p.code = s.plan_code
        WHERE k.key_hash = %s AND k.is_active
        ORDER BY s.current_period_end DESC NULLS LAST
        LIMIT 1
        """,
        (key_hash,),
    ).fetchone()
    if row is None:
        return None
    # 구독 없으면 free 로 폴백
    plan = row["plan_code"] or "free"
    ent = row["entitlements"]
    if ent is None:
        fb = conn.execute("SELECT entitlements FROM core.plans WHERE code='free'").fetchone()
        ent = fb["entitlements"] if fb else {}
    conn.execute("UPDATE core.api_keys SET last_used_at=now() WHERE key_hash=%s", (key_hash,))
    return TenantContext(tenant_id=row["tenant_id"], plan_code=plan, entitlements=ent)


def consume_quota(conn: Connection, tenant_id: int, metric: str, limit: Any) -> bool:
    """일 단위 사용량 계량 + 쿼터 검사(원자적). 허용 시 True."""
    if is_unlimited(limit):
        conn.execute(
            "INSERT INTO core.usage_counters (tenant_id, metric, period, used, quota) "
            "VALUES (%s,%s,CURRENT_DATE,1,NULL) "
            "ON CONFLICT (tenant_id, metric, period) DO UPDATE SET used = core.usage_counters.used + 1",
            (tenant_id, metric),
        )
        return True
    row = conn.execute(
        "INSERT INTO core.usage_counters (tenant_id, metric, period, used, quota) "
        "VALUES (%s,%s,CURRENT_DATE,1,%s) "
        "ON CONFLICT (tenant_id, metric, period) DO UPDATE SET used = core.usage_counters.used + 1 "
        "RETURNING used",
        (tenant_id, metric, int(limit)),
    ).fetchone()
    return int(row["used"]) <= int(limit)

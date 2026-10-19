"""관리자 겸 회원 계정 생성/갱신 — 비밀번호는 stdin 으로만 받는다.

왜 stdin 인가: 명령행 인자로 넘기면 `ps` 로 같은 호스트의 다른 사용자에게 보인다.
이 앱이 도는 서버는 여러 프로젝트가 함께 사는 공용 서버다. 비밀번호는 앱의
pbkdf2 해시로만 저장되고 원문은 로그·DB·파일 어디에도 남지 않는다.

만드는 것
  · 회원 계정  : core.users (role=owner) + tenant + 구독 + 포인트
  · 관리 권한  : admin 스코프 API 키 (플랫폼 전체 /growth/* 운영)

쓰임:
    printf '%s' '<비밀번호>' | python scripts/provision_admin.py <이메일> [표시이름]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

for _k, _v in {"GAMDAP_DB_HOST": "127.0.0.1", "GAMDAP_DB_PORT": "5432",
               "PYTHONIOENCODING": "utf-8"}.items():
    os.environ.setdefault(_k, _v)

from gamdap.api.auth import create_api_key  # noqa: E402
from gamdap.db import transaction  # noqa: E402
from gamdap.members import service  # noqa: E402
from gamdap.members.security import hash_password  # noqa: E402

PLAN = "vip"  # 운영자 계정이므로 최상위 등급(빌더 생성 포인트 포함)


def main() -> int:
    email = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    display = sys.argv[2] if len(sys.argv) > 2 else "TBURN 관리자"
    password = sys.stdin.readline().rstrip("\r\n")
    if not email or not password:
        print("이메일(인자)과 비밀번호(stdin)가 모두 필요합니다", file=sys.stderr)
        return 2

    with transaction() as conn:
        row = conn.execute(
            "SELECT id, tenant_id FROM core.users WHERE email=%s", (email,)).fetchone()

        if row:
            # 이미 있으면 비밀번호·권한만 갱신한다(기존 사이트·포인트는 보존).
            conn.execute(
                "UPDATE core.users SET password_hash=%s, role='owner', display_name=%s "
                "WHERE id=%s", (hash_password(password), display, row["id"]))
            tenant_id, user_id = row["tenant_id"], row["id"]
            print(f"기존 계정 갱신 — 비밀번호·권한 재설정 (user={user_id})")
        else:
            r = service.signup(conn, email, password, display_name=display, plan_code=PLAN)
            tenant_id, user_id = r["tenant_id"], r["user_id"]
            print(f"신규 가입 완료 (user={user_id}, 등급={r['plan']})")

        # 구독이 없거나 낮으면 운영자 등급을 보장한다.
        has_plan = conn.execute(
            "SELECT 1 FROM core.subscriptions WHERE tenant_id=%s AND plan_code=%s "
            "  AND status IN ('active','trialing')", (tenant_id, PLAN)).fetchone()
        if not has_plan:
            conn.execute(
                "INSERT INTO core.subscriptions (tenant_id, plan_code, status) "
                "VALUES (%s,%s,'active')", (tenant_id, PLAN))
            print(f"구독 {PLAN} 활성화")

        # 플랫폼 관리 권한 — admin 스코프 키. 원문은 이 출력에서만 볼 수 있다.
        held = conn.execute(
            "SELECT prefix FROM core.api_keys WHERE tenant_id=%s AND is_active "
            "  AND 'admin' = ANY(scopes) LIMIT 1", (tenant_id,)).fetchone()
        if held:
            print(f"관리자 키 이미 보유: {held['prefix']}…  (재발급은 기존 키 폐기 후)")
        else:
            k = create_api_key(conn, tenant_id=tenant_id,
                               label=f"{email} 관리자", scopes=["admin"])
            print("ADMIN_API_KEY=" + k["api_key"])

        info = conn.execute(
            "SELECT u.email, u.role, u.display_name, t.referral_code, "
            "       (SELECT plan_code FROM core.subscriptions WHERE tenant_id=t.id "
            "          AND status IN ('active','trialing') ORDER BY id DESC LIMIT 1) AS plan "
            "FROM core.users u JOIN core.tenants t ON t.id = u.tenant_id "
            "WHERE u.id=%s", (user_id,)).fetchone()
        pts = conn.execute(
            "SELECT COALESCE(balance,0) b FROM core.point_ledger WHERE tenant_id=%s "
            "ORDER BY id DESC LIMIT 1", (tenant_id,)).fetchone()

    print(f"계정  {info['email']}  ·  권한 {info['role']}  ·  등급 {info['plan']}  "
          f"·  포인트 {pts['b'] if pts else 0}")
    print(f"추천코드 {info['referral_code']}  ·  tenant {tenant_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

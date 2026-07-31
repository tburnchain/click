"""로컬 프리뷰 실행기 — 환경변수 내장(launch.json/미리보기 패널용).

실 PostgreSQL 클러스터(로컬 5433, 최신 시드 데이터: 회원사이트·10빌더 쇼케이스·수집상품)에
연결해 최신 페이지를 서빙한다. 포트는 harness 지정(PORT) 우선.
GAMDAP_DEMO 를 명시하면 DB 없이 DemoRepo 정적 데이터로 폴백한다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 최신 실데이터가 있는 로컬 클러스터(5433) 기본 연결. 각 값은 환경변수로 override 가능.
os.environ.setdefault("GAMDAP_DB_HOST", "127.0.0.1")
os.environ.setdefault("GAMDAP_DB_PORT", "5433")
os.environ.setdefault("GAMDAP_DB_NAME", "gamdap")
os.environ.setdefault("GAMDAP_DB_USER", "postgres")
os.environ.setdefault("GAMDAP_DB_PASSWORD", "x")
os.environ.setdefault("GAMDAP_MIGRATIONS_DIR", str(ROOT / "migrations"))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PGCLIENTENCODING", "UTF8")

# 콘솔 stdout이 cp949 등 비-UTF8이면 유니코드 출력이 깨지므로 재설정(best-effort).
import contextlib  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

import uvicorn  # noqa: E402

if __name__ == "__main__":
    # 로컬 DB가 재부팅 등으로 꺼져 있으면 best-effort 로 살린다('0건' 방지).
    try:
        from start_db import ensure_db  # scripts/ 에 위치
        print("[DB] connected" if ensure_db() else "[DB] auto-start failed - run: python scripts/start_db.py")
    except Exception as exc:  # noqa: BLE001
        print(f"[DB] check skipped: {exc}")

    port = int(os.environ.get("PORT", "8020"))
    uvicorn.run("gamdap.api.app:app", host="127.0.0.1", port=port, log_level="warning")

"""로컬 GAMDAP DB 클러스터 기동(멱등) — 재부팅 후 '0건' 방지용.

로컬 개발 클러스터(포트 5433, trust 인증)는 **프로젝트 디렉토리(.pgdata)** 에 있다.
과거엔 OS 임시 디렉토리에 있어 임시정리로 파일이 삭제돼 반복 손상됐다(pg_notify /
global/pg_filenode.map 등). 이제 임시경로 밖 영구 위치를 쓴다.
이 모듈은 5433 이 '실제 우리 클러스터'인지 확인하고, 아니면 pg_ctl 로 살린다.
serve_demo.py 가 부팅 시 best-effort 로 호출한다. 단독 실행도 가능:
    python scripts/start_db.py
"""

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

PG_BIN = Path(os.environ.get("GAMDAP_PG_BIN", r"C:/Program Files/PostgreSQL/17/bin"))
PORT = int(os.environ.get("GAMDAP_DB_PORT", "5433"))
# 프로젝트 루트의 영구 pgdata(임시정리 영향 없음)
PROJECT_PGDATA = Path(__file__).resolve().parents[1] / ".pgdata"


def reachable(port: int = PORT, host: str = "127.0.0.1") -> bool:
    """TCP 연결뿐 아니라 실제 gamdap 응답까지 확인(죽은 소켓 오탐 방지)."""
    with socket.socket() as s:
        s.settimeout(1.0)
        if s.connect_ex((host, port)) != 0:
            return False
    # 크래시한 postmaster 가 소켓만 물고 있는 경우를 걸러내려면 실제 질의가 필요.
    pg_isready = PG_BIN / "pg_isready.exe"
    if pg_isready.exists():
        try:
            r = subprocess.run([str(pg_isready), "-h", host, "-p", str(port),
                                "-d", os.environ.get("GAMDAP_DB_NAME", "gamdap")],
                               timeout=8, capture_output=True)
            return r.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False
    return True


def find_pgdata() -> str | None:
    """pgdata 위치: 환경변수 → 프로젝트 .pgdata(영구) → (레거시) Temp 스크래치패드."""
    env = os.environ.get("GAMDAP_PGDATA")
    if env and (Path(env) / "PG_VERSION").exists():
        return env
    if (PROJECT_PGDATA / "PG_VERSION").exists():
        return str(PROJECT_PGDATA)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        base = Path(local) / "Temp" / "claude"
        cands = sorted(base.glob("*/*/scratchpad/pgdata"),
                       key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        for p in cands:
            if (p / "PG_VERSION").exists():
                return str(p)
    return None


def ensure_db() -> bool:
    """5433 이 살아있으면 True. 꺼져 있으면 기동 시도 후 결과 반환."""
    if reachable():
        return True
    pgdata = find_pgdata()
    pg_ctl = PG_BIN / "pg_ctl.exe"
    if not pgdata or not pg_ctl.exists():
        return False
    log = str(Path(pgdata).parent / "pglog.txt")
    try:
        subprocess.run(
            [str(pg_ctl), "-D", pgdata, "-l", log, "-o", f"-p {PORT}", "-w", "start"],
            timeout=40, capture_output=True,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return reachable()


if __name__ == "__main__":
    if reachable():
        print(f"✓ DB 이미 실행 중 (127.0.0.1:{PORT})")
    elif ensure_db():
        print(f"✓ DB 기동 완료 (127.0.0.1:{PORT})")
    else:
        print("✗ DB 기동 실패 — pgdata 를 찾지 못했거나 pg_ctl 부재. "
              "GAMDAP_PGDATA 환경변수로 경로를 지정하세요.")
        raise SystemExit(1)

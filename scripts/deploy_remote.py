"""원격 서버 배포 헬퍼 — SSH 명령 실행(비밀번호는 env 로만 전달, 출력 금지).

사용:
  GAMDAP_DEPLOY_PASSWORD=... python scripts/deploy_remote.py "명령"
  GAMDAP_DEPLOY_PASSWORD=... python scripts/deploy_remote.py --script path/to/local.sh

환경변수:
  GAMDAP_DEPLOY_HOST (기본 31.97.8.11), GAMDAP_DEPLOY_USER (기본 root),
  GAMDAP_DEPLOY_PASSWORD (필수)
"""

from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("GAMDAP_DEPLOY_HOST", "31.97.8.11")
USER = os.environ.get("GAMDAP_DEPLOY_USER", "root")
PASSWORD = os.environ.get("GAMDAP_DEPLOY_PASSWORD", "")


def connect() -> paramiko.SSHClient:
    if not PASSWORD:
        print("GAMDAP_DEPLOY_PASSWORD 미설정", file=sys.stderr)
        raise SystemExit(2)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=30,
              allow_agent=False, look_for_keys=False)
    return c


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 600) -> int:
    """명령 실행 후 stdout/stderr 스트림 출력. 반환코드 리턴."""
    _in, out, err = client.exec_command(cmd, timeout=timeout, get_pty=False)
    for line in iter(out.readline, ""):
        sys.stdout.write(line)
    tail = err.read().decode("utf-8", "replace")
    if tail.strip():
        sys.stderr.write(tail)
    return out.channel.recv_exit_status()


def main() -> int:
    if len(sys.argv) < 2:
        print("사용: deploy_remote.py <명령> | --script <파일>", file=sys.stderr)
        return 2
    if sys.argv[1] == "--script":
        with open(sys.argv[2], encoding="utf-8") as f:
            cmd = "bash -s"
            body = f.read()
        client = connect()
        try:
            _in, out, err = client.exec_command(cmd, timeout=1800)
            _in.write(body)
            _in.channel.shutdown_write()
            for line in iter(out.readline, ""):
                sys.stdout.write(line)
            tail = err.read().decode("utf-8", "replace")
            if tail.strip():
                sys.stderr.write(tail)
            return out.channel.recv_exit_status()
        finally:
            client.close()
    client = connect()
    try:
        return run(client, " ".join(sys.argv[1:]))
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

#!/bin/sh
# GAMDAP 컨테이너 엔트리포인트
#   serve   : DB 대기 → (옵션)마이그레이션 → uvicorn API
#   worker  : DB 대기 → celery 워커(스케줄러/수집)
#   migrate : 마이그레이션만 실행 후 종료
set -e

wait_for_db() {
  echo "[entrypoint] waiting for database..."
  python - <<'PY'
import sys, time
import psycopg
from gamdap.config import get_settings
dsn = get_settings().db_dsn
for i in range(30):
    try:
        with psycopg.connect(dsn, connect_timeout=3) as c:
            c.execute("SELECT 1")
        print("[entrypoint] database ready")
        break
    except Exception as e:
        print(f"[entrypoint] db not ready ({i}): {e}")
        time.sleep(2)
else:
    sys.exit("[entrypoint] database unavailable")
PY
}

run_migrations() {
  if [ "${GAMDAP_RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[entrypoint] running migrations..."
    python -m gamdap.cli migrate
  fi
}

cmd="${1:-serve}"
case "$cmd" in
  serve)
    wait_for_db
    run_migrations
    exec uvicorn gamdap.api.app:app --host 0.0.0.0 --port 8000 --workers "${GAMDAP_WEB_CONCURRENCY:-2}"
    ;;
  worker)
    wait_for_db
    exec celery -A gamdap.worker.celery_app worker --loglevel=INFO
    ;;
  migrate)
    wait_for_db
    exec python -m gamdap.cli migrate
    ;;
  *)
    exec "$@"
    ;;
esac

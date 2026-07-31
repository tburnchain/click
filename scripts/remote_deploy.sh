#!/usr/bin/env bash
# GAMDAP 서버 배포 — 저장소 클론/갱신 → .env 생성 → 컨테이너 기동 → 헬스체크
set -euo pipefail

REPO="https://github.com/tburnchain/click.git"
APP_DIR="/opt/gamdap"

echo "▶ 1/6 저장소 준비"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --all -q && git -C "$APP_DIR" reset --hard origin/main -q
  echo "   기존 저장소 갱신 완료"
else
  rm -rf "$APP_DIR"
  git clone -q "$REPO" "$APP_DIR"
  echo "   클론 완료"
fi
cd "$APP_DIR"

echo "▶ 2/6 .env 생성(비밀은 서버에서 생성·보존)"
if [ ! -f .env ]; then
  DB_PW="$(openssl rand -hex 24)"
  APP_SECRET="$(openssl rand -hex 32)"
  cat > .env <<EOF
GAMDAP_ENV=production
GAMDAP_LOG_LEVEL=INFO
GAMDAP_DB_HOST=db
GAMDAP_DB_PORT=5432
GAMDAP_DB_NAME=gamdap
GAMDAP_DB_USER=gamdap
GAMDAP_DB_PASSWORD=${DB_PW}
GAMDAP_REDIS_URL=redis://redis:6379/0
GAMDAP_APP_SECRET=${APP_SECRET}
GAMDAP_RUN_MIGRATIONS=true
EOF
  chmod 600 .env
  echo "   .env 신규 생성(권한 600)"
else
  echo "   기존 .env 유지(비밀 보존)"
fi

echo "▶ 3/6 DB 포트 외부노출 차단(보안 오버라이드)"
cat > docker-compose.override.yml <<'EOF'
# 프로덕션 보안: DB/Redis 를 호스트 외부에 노출하지 않는다(내부 네트워크만).
services:
  db:
    ports: !override []
  redis:
    ports: !override []
  app:
    ports: !override
      - "127.0.0.1:8000:8000"
    restart: unless-stopped
  worker:
    restart: unless-stopped
EOF

echo "▶ 4/6 이미지 빌드(수 분 소요)"
docker compose build 2>&1 | tail -5

echo "▶ 5/6 컨테이너 기동"
docker compose up -d 2>&1 | tail -8

echo "▶ 6/6 헬스체크 대기"
for i in $(seq 1 30); do
  if curl -sf --max-time 5 http://127.0.0.1:8000/health >/dev/null 2>&1 \
     || curl -sf --max-time 5 http://127.0.0.1:8000/ >/dev/null 2>&1; then
    echo "   ✓ 앱 응답 정상"
    break
  fi
  sleep 5
  [ "$i" = "30" ] && echo "   ✗ 헬스체크 타임아웃"
done

echo "── 상태 ──"
docker compose ps --format "{{.Name}} | {{.State}} | {{.Ports}}" 2>&1

#!/usr/bin/env bash
# GAMDAP 리버스 프록시 구성 — nginx → 127.0.0.1:8000, 도메인 tburn.click
set -euo pipefail

DOMAIN="${DOMAIN:-tburn.click}"

echo "▶ 1/4 nginx 설치"
if ! command -v nginx >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >/dev/null 2>&1
  apt-get install -y -qq nginx >/dev/null 2>&1
  echo "   설치 완료"
else
  echo "   이미 설치됨"
fi

echo "▶ 2/4 사이트 설정"
cat > /etc/nginx/sites-available/gamdap <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} www.${DOMAIN};

    # Let's Encrypt 검증 경로
    location /.well-known/acme-challenge/ { root /var/www/html; }

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        # Cloudflare 종단 프로토콜 유지(리다이렉트 루프 방지)
        proxy_set_header X-Forwarded-Proto \$http_x_forwarded_proto;
        proxy_set_header Upgrade           \$http_upgrade;
        proxy_set_header Connection        "upgrade";
        proxy_read_timeout 120s;
    }
}
EOF
ln -sf /etc/nginx/sites-available/gamdap /etc/nginx/sites-enabled/gamdap
rm -f /etc/nginx/sites-enabled/default
mkdir -p /var/www/html

echo "▶ 3/4 설정 검증·반영"
nginx -t 2>&1 | tail -2
systemctl reload nginx 2>/dev/null || systemctl restart nginx
systemctl enable nginx >/dev/null 2>&1 || true

echo "▶ 4/4 방화벽 80/443 허용"
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null 2>&1 || true
  ufw allow 443/tcp >/dev/null 2>&1 || true
  echo "   ufw 규칙 추가"
else
  echo "   ufw 비활성(별도 조치 불필요)"
fi

echo "── 검증 ──"
echo -n "로컬 프록시: "; curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 10 -H "Host: ${DOMAIN}" http://127.0.0.1/

# ─────────────────────────────────────────────────────────────
# GAMDAP 프로덕션 이미지 (멀티스테이지)
#  stage 1: React 대시보드 빌드(node)
#  stage 2: Python 런타임 + 정적 프런트 포함
# ─────────────────────────────────────────────────────────────

# --- stage 1: frontend ---
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- stage 2: app ---
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    GAMDAP_MIGRATIONS_DIR=/app/migrations \
    GAMDAP_LOG_JSON=true
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# 의존성 레이어 캐시: 소스보다 먼저 메타데이터 복사
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e .

COPY migrations ./migrations
COPY docker/entrypoint.sh /entrypoint.sh
COPY --from=frontend /fe/dist ./frontend/dist
RUN chmod +x /entrypoint.sh

# 비루트 실행
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["serve"]

-- 0004 · AI 어시스트 플레인(플러그형, 관리자 제어, 기본 OFF)
-- 원칙: AI는 T1(가격/재고/수수료)을 절대 수정 못 함 → 제안만 남기고 승인 게이트를 거친다.

CREATE TABLE IF NOT EXISTS core.ai_providers (
    id                  SERIAL PRIMARY KEY,
    code                TEXT UNIQUE NOT NULL,      -- 'openai','anthropic','local_llm',...
    display_name        TEXT NOT NULL,
    adapter             TEXT NOT NULL,             -- 어댑터 구현 식별자
    base_url            TEXT,
    secret_ref          TEXT,                      -- 시크릿매니저 키 참조(원문 금지)
    is_enabled          BOOLEAN NOT NULL DEFAULT FALSE,
    monthly_budget_usd  NUMERIC(10,2),
    rate_limit_per_min  INT,
    config              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.ai_capabilities (
    id           SERIAL PRIMARY KEY,
    provider_id  INT NOT NULL REFERENCES core.ai_providers(id),
    capability   TEXT NOT NULL CHECK (capability IN
                   ('category_mapping','entity_matching','translation',
                    'trend_signal','crawl_assist','change_tracking','embedding','discovery')),
    is_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    priority     INT NOT NULL DEFAULT 100,         -- 낮을수록 우선(라우팅/폴백)
    params       JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (provider_id, capability)
);

CREATE TABLE IF NOT EXISTS core.ai_suggestions (
    id           BIGSERIAL PRIMARY KEY,
    provider_id  INT REFERENCES core.ai_providers(id),
    capability   TEXT NOT NULL,
    target_type  TEXT,                             -- 'network_category'|'product_match'|'taxonomy'|'offer_signal'
    target_id    TEXT,
    suggestion   JSONB NOT NULL,
    confidence   NUMERIC(3,2),
    status       TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','accepted','rejected','auto_applied')),
    reviewed_by  BIGINT,
    reviewed_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ai_sugg_status ON core.ai_suggestions(status, created_at);

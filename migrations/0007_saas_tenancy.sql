-- 0007 · SaaS 구독 · 멀티테넌시(§19) — 공유 카탈로그 + 테넌트별 엔타이틀먼트 + RLS

CREATE TABLE IF NOT EXISTS core.tenants (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    owner_email TEXT,
    status      TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','suspended','canceled')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.plans (
    code            TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    price_monthly_usd NUMERIC(10,2) NOT NULL DEFAULT 0,
    entitlements    JSONB NOT NULL DEFAULT '{}'::jsonb
);

INSERT INTO core.plans (code, display_name, price_monthly_usd, entitlements) VALUES
    ('free','Free',0,
     '{"networks":1,"freshness":"daily","max_alerts":3,"api_rpm":0,"export":false,"seats":1,"advanced_analytics":false}'::jsonb),
    ('starter','Starter',29,
     '{"networks":3,"freshness":"12h","max_alerts":20,"api_rpm":30,"export":"limited","seats":3,"advanced_analytics":true}'::jsonb),
    ('pro','Pro',99,
     '{"networks":"*","freshness":"hot","max_alerts":-1,"api_rpm":120,"export":true,"seats":10,"advanced_analytics":true}'::jsonb),
    ('enterprise','Enterprise',0,
     '{"networks":"*","freshness":"hot","max_alerts":-1,"api_rpm":-1,"export":true,"seats":-1,"advanced_analytics":true,"sla":true}'::jsonb)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS core.subscriptions (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           BIGINT NOT NULL REFERENCES core.tenants(id),
    plan_code           TEXT NOT NULL REFERENCES core.plans(code),
    status              TEXT NOT NULL DEFAULT 'trialing'
                          CHECK (status IN ('trialing','active','past_due','canceled')),
    billing_provider    TEXT NOT NULL DEFAULT 'stripe',
    external_sub_id     TEXT,
    current_period_end  TIMESTAMPTZ,
    seats               INT NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_subs_tenant ON core.subscriptions(tenant_id);

CREATE TABLE IF NOT EXISTS core.users (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   BIGINT REFERENCES core.tenants(id),
    email       TEXT UNIQUE NOT NULL,
    role        TEXT NOT NULL DEFAULT 'viewer'
                  CHECK (role IN ('owner','admin','analyst','viewer')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.usage_counters (
    tenant_id  BIGINT NOT NULL REFERENCES core.tenants(id),
    metric     TEXT NOT NULL,           -- 'api_calls'|'exports'|'alerts_active'
    period     DATE NOT NULL,
    used       BIGINT NOT NULL DEFAULT 0,
    quota      BIGINT,
    PRIMARY KEY (tenant_id, metric, period)
);

-- 테넌트 격리 데이터(저장뷰/알림) + RLS
CREATE TABLE IF NOT EXISTS core.saved_views (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  BIGINT NOT NULL REFERENCES core.tenants(id),
    user_id    BIGINT REFERENCES core.users(id),
    name       TEXT,
    filter     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS core.alerts (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  BIGINT NOT NULL REFERENCES core.tenants(id),
    user_id    BIGINT REFERENCES core.users(id),
    condition  JSONB NOT NULL,
    channel    TEXT,                    -- 'email'|'slack'
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Row-Level Security: 앱은 SET app.tenant_id = <id> 후 조회 → 크로스테넌트 차단
ALTER TABLE core.saved_views ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.alerts      ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_saved_views_tenant ON core.saved_views;
CREATE POLICY p_saved_views_tenant ON core.saved_views
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::bigint);

DROP POLICY IF EXISTS p_alerts_tenant ON core.alerts;
CREATE POLICY p_alerts_tenant ON core.alerts
    USING (tenant_id = current_setting('app.tenant_id', TRUE)::bigint);

-- 감사 로그
CREATE TABLE IF NOT EXISTS core.audit_logs (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  BIGINT,
    user_id    BIGINT,
    action     TEXT NOT NULL,
    target     TEXT,
    detail     JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

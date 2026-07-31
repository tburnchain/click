-- 0011 · 테넌트 API 키(멀티테넌시 인증, §19) — 원문 키 저장 금지(해시만)

CREATE TABLE IF NOT EXISTS core.api_keys (
    id           BIGSERIAL PRIMARY KEY,
    tenant_id    BIGINT NOT NULL REFERENCES core.tenants(id),
    key_hash     TEXT UNIQUE NOT NULL,         -- sha256(raw_key)
    label        TEXT,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_apikeys_tenant ON core.api_keys(tenant_id);

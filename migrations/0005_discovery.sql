-- 0005 · 자가확장 발견 엔진(§16) · 애그리게이터 우선 편입 정책
-- 발견은 "후보 생성"까지만. 공식/애그리게이터 API·승인 피드를 갖춰야만 커넥터로 승격.

CREATE TABLE IF NOT EXISTS core.discovery_sources (
    id               SERIAL PRIMARY KEY,
    code             TEXT UNIQUE NOT NULL,
    kind             TEXT NOT NULL CHECK (kind IN ('aggregator','directory','merchant_page','ai','manual')),
    url              TEXT,
    trust            NUMERIC(3,2) NOT NULL DEFAULT 0.5,
    provides_api     BOOLEAN NOT NULL DEFAULT FALSE,   -- 애그리게이터=대부분 TRUE
    is_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    last_scanned_at  TIMESTAMPTZ,
    meta             JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS core.network_candidates (
    id                   BIGSERIAL PRIMARY KEY,
    name                 TEXT NOT NULL,
    home_url             TEXT,
    program_url          TEXT,
    country_iso          CHAR(2),
    discovered_by        INT REFERENCES core.discovery_sources(id),

    -- 검증 시그널
    has_official_api     BOOLEAN,
    api_doc_url          TEXT,
    has_product_feed     BOOLEAN,
    feed_url             TEXT,
    terms_scrape_allowed BOOLEAN,
    deeplink_policy      TEXT,
    est_commission_hint  TEXT,
    category_fit         NUMERIC(3,2),
    commission_viability NUMERIC(3,2),
    country_priority     NUMERIC(3,2),
    duplicate_of         INT REFERENCES core.networks(id),

    candidate_score      NUMERIC(6,3),
    status               TEXT NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending','vetting','approved','onboarded','rejected')),
    reviewed_by          BIGINT,
    reviewed_at          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cand_status ON core.network_candidates(status);
CREATE INDEX IF NOT EXISTS idx_cand_score  ON core.network_candidates(candidate_score DESC);

-- UCB 탐사 밴딧 상태(§16.3): arm = (network_code, category_slug)
CREATE TABLE IF NOT EXISTS core.discovery_arms (
    id             BIGSERIAL PRIMARY KEY,
    arm_key        TEXT UNIQUE NOT NULL,       -- 'coupang_partners::electronics'
    network_code   TEXT,
    category_slug  TEXT,
    pulls          BIGINT NOT NULL DEFAULT 0,  -- n(arm)
    reward_sum     NUMERIC(18,6) NOT NULL DEFAULT 0,
    reward_mean    NUMERIC(18,6) NOT NULL DEFAULT 0,
    last_pulled_at TIMESTAMPTZ
);

-- ── 시드: 애그리게이터 우선 편입 소스 ────────────────
-- 공식 API를 제공하는 글로벌 애그리게이터를 최상위 신뢰도로 우선 편입한다.
INSERT INTO core.discovery_sources (code, kind, url, trust, provides_api, meta) VALUES
    ('cj_affiliate',  'aggregator', 'https://www.cj.com',            0.95, TRUE,
        '{"api":"CJ Link/Product REST + GraphQL","regions":["US","Gglobal"],"priority":1}'::jsonb),
    ('impact',        'aggregator', 'https://impact.com',            0.95, TRUE,
        '{"api":"Impact Partnership Cloud API","regions":["Global"],"priority":1}'::jsonb),
    ('rakuten',       'aggregator', 'https://rakutenadvertising.com',0.92, TRUE,
        '{"api":"Rakuten Advertising API","regions":["US","JP","Global"],"priority":2}'::jsonb),
    ('awin',          'aggregator', 'https://www.awin.com',          0.92, TRUE,
        '{"api":"Awin Publisher API + Product Feeds","regions":["EU","Global"],"priority":2}'::jsonb),
    ('coupang_dir',   'aggregator', 'https://partners.coupang.com',  0.90, TRUE,
        '{"api":"Coupang Partners OpenAPI","regions":["KR"],"priority":1}'::jsonb),
    ('amazon_dir',    'aggregator', 'https://affiliate-program.amazon.com', 0.88, TRUE,
        '{"api":"Amazon PA-API v5","regions":["US","Global"],"priority":2}'::jsonb),
    ('clickbank_dir', 'aggregator', 'https://www.clickbank.com',     0.85, TRUE,
        '{"api":"ClickBank Marketplace API","regions":["US","Global"],"priority":3}'::jsonb)
ON CONFLICT (code) DO NOTHING;

-- ── 시드: 네트워크(우리가 커넥터를 갖춘/우선 구축할 대상) ──
INSERT INTO core.networks (code, display_name, home_country_id, data_source, adapter, api_base_url, is_active)
SELECT 'coupang_partners', '쿠팡 파트너스', c.id, 'official_api', 'coupang',
       'https://api-gateway.coupang.com', TRUE
FROM core.countries c WHERE c.iso_code = 'KR'
ON CONFLICT (code) DO NOTHING;

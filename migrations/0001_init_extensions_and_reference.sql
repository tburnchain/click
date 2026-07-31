-- 0001 · 확장 + 참조 데이터 (스키마: core / bronze / analytics)
-- 멱등성: 모든 객체는 IF NOT EXISTS. 마이그레이션 러너가 트랜잭션으로 감싼다.

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS analytics;

-- 계층 카테고리(ltree), 유사도 검색(pg_trgm)
CREATE EXTENSION IF NOT EXISTS ltree;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── 국가 ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.countries (
    id                SERIAL PRIMARY KEY,
    iso_code          CHAR(2) UNIQUE NOT NULL,
    name              TEXT NOT NULL,
    default_currency  CHAR(3) NOT NULL
);

-- ── 네트워크(제휴사) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS core.networks (
    id                SERIAL PRIMARY KEY,
    code              TEXT UNIQUE NOT NULL,            -- 'coupang_partners','amazon_assoc',...
    display_name      TEXT NOT NULL,
    home_country_id   INT REFERENCES core.countries(id),
    data_source       TEXT NOT NULL DEFAULT 'official_api'
                        CHECK (data_source IN ('official_api','aggregator_api','feed')),
    adapter           TEXT,                            -- 커넥터 어댑터 식별자
    api_base_url      TEXT,
    terms_url         TEXT,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    meta              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 통합 택소노미(자기참조 계층) ─────────────────────
CREATE TABLE IF NOT EXISTS core.categories (
    id          SERIAL PRIMARY KEY,
    parent_id   INT REFERENCES core.categories(id),
    slug        TEXT UNIQUE NOT NULL,
    name_ko     TEXT,
    name_en     TEXT,
    path        LTREE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_categories_path ON core.categories USING gist (path);

-- ── 네트워크 원본 카테고리 → 통합 매핑 ───────────────
CREATE TABLE IF NOT EXISTS core.network_categories (
    id                  SERIAL PRIMARY KEY,
    network_id          INT NOT NULL REFERENCES core.networks(id),
    raw_name            TEXT NOT NULL,
    category_id         INT REFERENCES core.categories(id),
    mapping_confidence  NUMERIC(3,2) NOT NULL DEFAULT 1.0,
    mapped_by           TEXT NOT NULL DEFAULT 'rule'      -- 'rule'|'ai_suggested'|'human'
                          CHECK (mapped_by IN ('rule','ai_suggested','human')),
    UNIQUE (network_id, raw_name)
);

-- ── 환율(as_of 이력) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS core.exchange_rates (
    base_currency   CHAR(3) NOT NULL,
    quote_currency  CHAR(3) NOT NULL,
    rate            NUMERIC(18,8) NOT NULL,
    as_of           DATE NOT NULL,
    source          TEXT,
    PRIMARY KEY (base_currency, quote_currency, as_of)
);

-- ── 시드: 국가 ───────────────────────────────────────
INSERT INTO core.countries (iso_code, name, default_currency) VALUES
    ('KR','대한민국','KRW'),
    ('US','United States','USD'),
    ('JP','Japan','JPY'),
    ('GB','United Kingdom','GBP')
ON CONFLICT (iso_code) DO NOTHING;

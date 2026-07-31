-- 0002 · 상품 카탈로그 · 오퍼(심장) · 수수료 정책 · 가격 이력(월 파티션)

-- ── 상품(네트워크 간 통합 실물) ─────────────────────
CREATE TABLE IF NOT EXISTS core.products (
    id                 BIGSERIAL PRIMARY KEY,
    canonical_name     TEXT NOT NULL,
    brand              TEXT,
    gtin               TEXT,
    category_id        INT REFERENCES core.categories(id),
    primary_image_url  TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_products_gtin
    ON core.products(gtin) WHERE gtin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_products_name_trgm
    ON core.products USING gin (canonical_name gin_trgm_ops);

CREATE TABLE IF NOT EXISTS core.product_translations (
    product_id   BIGINT NOT NULL REFERENCES core.products(id),
    lang         CHAR(2) NOT NULL,
    name         TEXT,
    description  TEXT,
    source       TEXT NOT NULL DEFAULT 'official',
    confidence   NUMERIC(3,2) NOT NULL DEFAULT 1.0,
    PRIMARY KEY (product_id, lang)
);

-- ── 오퍼(네트워크별 판매/정산 조건) ─────────────────
CREATE TABLE IF NOT EXISTS core.offers (
    id                       BIGSERIAL PRIMARY KEY,
    network_id               INT NOT NULL REFERENCES core.networks(id),
    external_product_id      TEXT NOT NULL,
    product_id               BIGINT REFERENCES core.products(id),
    title                    TEXT NOT NULL,
    landing_url              TEXT,
    thumbnail_url            TEXT,

    -- 가격(원자적: amount + currency, 파생: krw/usd)
    price_amount             NUMERIC(18,4),
    price_currency           CHAR(3),
    price_krw                NUMERIC(18,4),
    price_usd                NUMERIC(18,4),

    -- 과금/수수료
    billing_type             TEXT CHECK (billing_type IN ('CPS','CPC','CPM','CPA','CPL')),
    commission_kind          TEXT CHECK (commission_kind IN ('percent','fixed')),
    commission_rate          NUMERIC(6,4),          -- percent: 0.03 = 3%
    commission_fixed_amount  NUMERIC(18,4),
    commission_currency      CHAR(3),

    -- 재고/가용성
    stock_status             TEXT CHECK (stock_status IN
                               ('in_stock','low','out_of_stock','digital_unlimited','unknown')),
    stock_quantity           INT,
    is_active                BOOLEAN NOT NULL DEFAULT TRUE,
    delisted_at              TIMESTAMPTZ,

    -- 공식 API 네이티브 인기 지표(수요 신호의 원천)
    native_rank              INT,
    native_metric_json       JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- 데이터 거버넌스
    data_source              TEXT NOT NULL DEFAULT 'official_api',
    fetched_at               TIMESTAMPTZ NOT NULL,
    raw_ref                  BIGINT,
    needs_review             BOOLEAN NOT NULL DEFAULT FALSE,

    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (network_id, external_product_id)        -- 자연키(UPSERT 기준)
);
CREATE INDEX IF NOT EXISTS idx_offers_network ON core.offers(network_id);
CREATE INDEX IF NOT EXISTS idx_offers_product ON core.offers(product_id);
CREATE INDEX IF NOT EXISTS idx_offers_active  ON core.offers(is_active) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_offers_fetched ON core.offers(fetched_at);
CREATE INDEX IF NOT EXISTS idx_offers_review  ON core.offers(needs_review) WHERE needs_review;

-- ── 카테고리별 수수료 정책(메타) ────────────────────
CREATE TABLE IF NOT EXISTS core.commission_rules (
    id               SERIAL PRIMARY KEY,
    network_id       INT REFERENCES core.networks(id),
    category_id      INT REFERENCES core.categories(id),
    billing_type     TEXT,
    commission_kind  TEXT,
    rate             NUMERIC(6,4),
    fixed_amount     NUMERIC(18,4),
    currency         CHAR(3),
    country_id       INT REFERENCES core.countries(id),
    effective_from   DATE,
    effective_to     DATE,
    data_source      TEXT NOT NULL DEFAULT 'official_api'
);

-- ── 가격/수수료/재고 변동 이력(월 RANGE 파티션) ────
CREATE TABLE IF NOT EXISTS core.price_history (
    id                       BIGSERIAL,
    offer_id                 BIGINT NOT NULL REFERENCES core.offers(id),
    observed_at              TIMESTAMPTZ NOT NULL,
    price_amount             NUMERIC(18,4),
    price_currency           CHAR(3),
    commission_rate          NUMERIC(6,4),
    commission_fixed_amount  NUMERIC(18,4),
    stock_status             TEXT,
    stock_quantity           INT,
    PRIMARY KEY (id, observed_at)
) PARTITION BY RANGE (observed_at);

-- 초기 파티션(당월/익월). 운영은 파티션 자동생성 잡으로 관리(§운영).
CREATE TABLE IF NOT EXISTS core.price_history_default
    PARTITION OF core.price_history DEFAULT;
CREATE INDEX IF NOT EXISTS idx_price_history_offer
    ON core.price_history(offer_id, observed_at DESC);

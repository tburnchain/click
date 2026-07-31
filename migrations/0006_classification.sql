-- 0006 · 광고상품 분류 엔진(§18) — 다축 분류 · 기회 사분면 · 니치 군집
-- 이식성: 임베딩은 double precision[]로 저장(폴백). 대규모 ANN 필요 시 pgvector로 교체.

CREATE TABLE IF NOT EXISTS core.taxonomy_axes (
    id      SERIAL PRIMARY KEY,
    axis    TEXT UNIQUE NOT NULL,     -- 'intent','price_tier','audience','seasonality'
    values  JSONB NOT NULL DEFAULT '[]'::jsonb
);

INSERT INTO core.taxonomy_axes (axis, values) VALUES
    ('intent',      '["problem_solving","impulse","considered","gift"]'::jsonb),
    ('price_tier',  '["budget","mid","premium"]'::jsonb),
    ('seasonality', '["evergreen","seasonal","event"]'::jsonb)
ON CONFLICT (axis) DO NOTHING;

CREATE TABLE IF NOT EXISTS analytics.product_classifications (
    offer_id             BIGINT PRIMARY KEY REFERENCES core.offers(id),
    category_id          INT REFERENCES core.categories(id),
    category_confidence  NUMERIC(4,3),
    intent               TEXT,
    price_tier           TEXT,
    audience             JSONB,
    seasonality          TEXT,
    competition_index    NUMERIC(6,3),
    opportunity_score    NUMERIC(6,3),
    segment              TEXT CHECK (segment IN
                           ('goldmine','rising','cashcow','saturated','avoid')),
    trend_slope          NUMERIC(8,5),
    embedding            DOUBLE PRECISION[],       -- 폴백 저장(TF-IDF/임베딩)
    method               TEXT,                     -- 'rule'|'embedding'|'tfidf_fallback'
    classified_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pc_segment ON analytics.product_classifications(segment);
CREATE INDEX IF NOT EXISTS idx_pc_opportunity
    ON analytics.product_classifications(opportunity_score DESC);

-- 니치/군집 단위 집계(경쟁·포화 수학 §18.5)
CREATE TABLE IF NOT EXISTS analytics.niche_clusters (
    id                 BIGSERIAL PRIMARY KEY,
    label              TEXT,
    centroid           DOUBLE PRECISION[],
    size               INT,
    coherence          NUMERIC(4,3),
    supply             NUMERIC(6,3),
    hhi                NUMERIC(4,3),
    entropy            NUMERIC(6,3),
    competition_index  NUMERIC(6,3),
    avg_opportunity    NUMERIC(6,3),
    status             TEXT NOT NULL DEFAULT 'active',
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 카테고리 중심점(EMA 자기학습, §18.3)
CREATE TABLE IF NOT EXISTS analytics.category_centroids (
    category_id  INT PRIMARY KEY REFERENCES core.categories(id),
    centroid     DOUBLE PRECISION[],
    n_samples    BIGINT NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

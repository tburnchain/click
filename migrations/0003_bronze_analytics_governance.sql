-- 0003 · Bronze(원본 불변) · Analytics(파생) · 운영/관측 · 트리거

-- ── Bronze: 외부 원본 그대로 보존(불변) ─────────────
CREATE TABLE IF NOT EXISTS bronze.raw_payloads (
    id            BIGSERIAL PRIMARY KEY,
    network_code  TEXT,
    source        TEXT,                 -- 'coupang_api','amazon_paapi',...
    request       JSONB,
    response      JSONB,
    http_status   INT,
    cost_usd      NUMERIC(10,6),
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_raw_network_time
    ON bronze.raw_payloads(network_code, fetched_at DESC);

-- ── Analytics: 수익성 점수(사전계산) ────────────────
CREATE TABLE IF NOT EXISTS analytics.profitability_scores (
    offer_id                   BIGINT PRIMARY KEY REFERENCES core.offers(id),
    expected_earning_per_sale  NUMERIC(18,4),
    expected_epc               NUMERIC(18,6),
    demand_index               NUMERIC(6,3),
    competition_index          NUMERIC(6,3),
    freshness_factor           NUMERIC(4,3),
    profitability_score        NUMERIC(7,3),
    computed_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_prof_score
    ON analytics.profitability_scores(profitability_score DESC);

-- ── 운영: 수집 작업 로그 ────────────────────────────
CREATE TABLE IF NOT EXISTS core.ingestion_jobs (
    id             BIGSERIAL PRIMARY KEY,
    network_code   TEXT,
    job_type       TEXT,                 -- 'full'|'incremental'|'category'|'backfill'
    status         TEXT NOT NULL DEFAULT 'running'
                     CHECK (status IN ('running','success','failed','partial')),
    params         JSONB NOT NULL DEFAULT '{}'::jsonb,
    rows_upserted  INT NOT NULL DEFAULT 0,
    rows_changed   INT NOT NULL DEFAULT 0,
    cost_usd       NUMERIC(10,6) NOT NULL DEFAULT 0,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    error          TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON core.ingestion_jobs(status, started_at DESC);

-- ── 관측: 외부/AI 호출 로그(월 파티션) ──────────────
CREATE TABLE IF NOT EXISTS core.api_call_logs (
    id           BIGSERIAL,
    provider     TEXT,
    kind         TEXT,                   -- 'official_api'|'ai_assist'
    capability   TEXT,
    request      JSONB,
    http_status  INT,
    latency_ms   INT,
    cost_usd     NUMERIC(10,6),
    called_at    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id, called_at)
) PARTITION BY RANGE (called_at);
CREATE TABLE IF NOT EXISTS core.api_call_logs_default
    PARTITION OF core.api_call_logs DEFAULT;

-- ── 트리거: 오퍼 UPSERT 시 변동을 price_history에 적재 ──
-- (부록 A의 "변경분만 이력화"를 DB 레벨에서 이중 보장)
CREATE OR REPLACE FUNCTION core.fn_offers_history() RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'INSERT')
       OR (NEW.price_amount            IS DISTINCT FROM OLD.price_amount)
       OR (NEW.commission_rate         IS DISTINCT FROM OLD.commission_rate)
       OR (NEW.commission_fixed_amount IS DISTINCT FROM OLD.commission_fixed_amount)
       OR (NEW.stock_status            IS DISTINCT FROM OLD.stock_status)
       OR (NEW.stock_quantity          IS DISTINCT FROM OLD.stock_quantity)
    THEN
        INSERT INTO core.price_history (
            offer_id, observed_at, price_amount, price_currency,
            commission_rate, commission_fixed_amount, stock_status, stock_quantity)
        VALUES (
            NEW.id, NEW.fetched_at, NEW.price_amount, NEW.price_currency,
            NEW.commission_rate, NEW.commission_fixed_amount, NEW.stock_status, NEW.stock_quantity);
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_offers_history ON core.offers;
CREATE TRIGGER trg_offers_history
    BEFORE INSERT OR UPDATE ON core.offers
    FOR EACH ROW EXECUTE FUNCTION core.fn_offers_history();

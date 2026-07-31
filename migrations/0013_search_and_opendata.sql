-- 0013 · 검색 초고도화(FTS tsvector + 트라이그램) + 공개데이터 네트워크 시드

-- 전문검색 벡터(생성 컬럼, 자동 유지) — title 기반
ALTER TABLE core.offers ADD COLUMN IF NOT EXISTS search_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', coalesce(title, ''))) STORED;

-- FTS GIN 인덱스 + 퍼지(오타 허용) 트라이그램 GIN
CREATE INDEX IF NOT EXISTS idx_offers_tsv
    ON core.offers USING gin (search_tsv);
CREATE INDEX IF NOT EXISTS idx_offers_title_trgm
    ON core.offers USING gin (title gin_trgm_ops);

-- 공개 데이터 커넥터(키리스 실검색 실증) 네트워크 시드
INSERT INTO core.networks (code, display_name, home_country_id, data_source, adapter, api_base_url, is_active)
SELECT 'opendata', '공개데이터(샌드박스)', c.id, 'feed', 'opendata', 'https://dummyjson.com', TRUE
FROM core.countries c WHERE c.iso_code = 'US'
ON CONFLICT (code) DO UPDATE SET adapter = EXCLUDED.adapter, data_source = EXCLUDED.data_source;

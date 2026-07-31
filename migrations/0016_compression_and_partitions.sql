-- 0016 · 대용량 저장 최적화 — zstd 애플리케이션 압축 + PG17 lz4 TOAST + 파티션 준비
-- 크롤 payload(raw_payloads)·이력·로그가 폭증 → 이중 압축 전략.

-- ① raw_payloads: 응답을 zstd 압축 bytea 로 저장(원본 jsonb는 폐기 대상, 신규는 NULL)
ALTER TABLE bronze.raw_payloads ADD COLUMN IF NOT EXISTS response_zstd BYTEA;
ALTER TABLE bronze.raw_payloads ADD COLUMN IF NOT EXISTS orig_bytes INT;
ALTER TABLE bronze.raw_payloads ADD COLUMN IF NOT EXISTS comp_bytes INT;
ALTER TABLE bronze.raw_payloads ALTER COLUMN response DROP NOT NULL;

-- ② PG17 네이티브 lz4 TOAST — 남는 JSONB 컬럼(request 등)에 적용(pglz보다 빠름)
ALTER TABLE bronze.raw_payloads ALTER COLUMN request SET COMPRESSION lz4;
ALTER TABLE core.api_call_logs   ALTER COLUMN request SET COMPRESSION lz4;
ALTER TABLE core.offers          ALTER COLUMN native_metric_json SET COMPRESSION lz4;

-- ③ 압축 딕셔너리 저장(유사 payload용 zstd 사전, 소스별 1개)
CREATE TABLE IF NOT EXISTS bronze.zstd_dictionaries (
    source      TEXT PRIMARY KEY,
    dict_bytes  BYTEA NOT NULL,
    trained_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    sample_n    INT
);

-- ④ 압축 절감 관측 뷰
CREATE OR REPLACE VIEW bronze.compression_stats AS
SELECT source,
       count(*)                          AS payloads,
       COALESCE(sum(orig_bytes),0)       AS orig_total,
       COALESCE(sum(comp_bytes),0)       AS comp_total,
       CASE WHEN COALESCE(sum(comp_bytes),0)=0 THEN 0
            ELSE round(sum(orig_bytes)::numeric / sum(comp_bytes), 2) END AS ratio
FROM bronze.raw_payloads
WHERE response_zstd IS NOT NULL
GROUP BY source;

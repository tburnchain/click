-- 0009 · 애그리게이터 네트워크 시드(M5) — CJ · Impact
-- 애그리게이터 우선 편입(§16.5): 다수 머천트를 단일 공식 API로 노출.

INSERT INTO core.networks (code, display_name, home_country_id, data_source, adapter, api_base_url, is_active)
SELECT 'cj_affiliate', 'CJ Affiliate', c.id, 'aggregator_api', 'cj', 'https://ads.api.cj.com', TRUE
FROM core.countries c WHERE c.iso_code = 'US'
ON CONFLICT (code) DO UPDATE SET adapter = EXCLUDED.adapter, data_source = EXCLUDED.data_source;

INSERT INTO core.networks (code, display_name, home_country_id, data_source, adapter, api_base_url, is_active)
SELECT 'impact', 'Impact', c.id, 'aggregator_api', 'impact', 'https://api.impact.com', TRUE
FROM core.countries c WHERE c.iso_code = 'US'
ON CONFLICT (code) DO UPDATE SET adapter = EXCLUDED.adapter, data_source = EXCLUDED.data_source;

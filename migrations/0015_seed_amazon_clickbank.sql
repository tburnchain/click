-- 0015 · Amazon·ClickBank 네트워크 시드(커넥터 구현 완료)

INSERT INTO core.networks (code, display_name, home_country_id, data_source, adapter, api_base_url, is_active)
SELECT 'amazon_assoc', 'Amazon Associates', c.id, 'aggregator_api', 'amazon',
       'https://webservices.amazon.com', TRUE
FROM core.countries c WHERE c.iso_code = 'US'
ON CONFLICT (code) DO UPDATE SET adapter = EXCLUDED.adapter, data_source = EXCLUDED.data_source;

INSERT INTO core.networks (code, display_name, home_country_id, data_source, adapter, api_base_url, is_active)
SELECT 'clickbank', 'ClickBank', c.id, 'aggregator_api', 'clickbank',
       'https://api.clickbank.com', TRUE
FROM core.countries c WHERE c.iso_code = 'US'
ON CONFLICT (code) DO UPDATE SET adapter = EXCLUDED.adapter, data_source = EXCLUDED.data_source;

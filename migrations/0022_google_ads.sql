-- 0022 · 구글광고(Google Ads) 전용 패키지 — 고전환 랜딩 + GA4·전환추적·리마케팅·UTM/gclid.
-- 새 빌더 kind 'google_ads' 추가 + 템플릿 시드.

ALTER TABLE core.builder_templates DROP CONSTRAINT IF EXISTS builder_templates_kind_check;
ALTER TABLE core.builder_templates ADD CONSTRAINT builder_templates_kind_check
  CHECK (kind IN ('shopping','search','general','enterprise','mixed','article',
                  'deal','ranking','coupon','boutique','blog','directory','google_ads'));

INSERT INTO core.builder_templates (code, name, kind, point_cost, complexity, description, config) VALUES
  ('google_ads_lp', '구글광고 전용 랜딩', 'google_ads', 45, 4,
   'Google Ads 전용 고전환 랜딩페이지 — GA4·전환추적·리마케팅·UTM/gclid 완전 추적',
   '{"accent":"#1a73e8","gads":true}'::jsonb)
ON CONFLICT (code) DO UPDATE SET point_cost=EXCLUDED.point_cost, complexity=EXCLUDED.complexity,
  name=EXCLUDED.name, description=EXCLUDED.description, config=EXCLUDED.config, kind=EXCLUDED.kind;

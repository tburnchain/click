-- 0020 · 빌더 사이트 6종 추가(총 10 스타일). 제휴마케터가 직접 운영하는 느낌의 실사이트 유형.
-- kind CHECK 제약을 확장하고 신규 템플릿을 시드한다.

ALTER TABLE core.builder_templates DROP CONSTRAINT IF EXISTS builder_templates_kind_check;
ALTER TABLE core.builder_templates ADD CONSTRAINT builder_templates_kind_check
  CHECK (kind IN ('shopping','search','general','enterprise','mixed','article',
                  'deal','ranking','coupon','boutique','blog','directory'));

ALTER TABLE core.member_sites DROP CONSTRAINT IF EXISTS member_sites_kind_check;  -- (있으면)

INSERT INTO core.builder_templates (code, name, kind, point_cost, complexity, description, config) VALUES
  ('deal_flash',       '핫딜·타임특가형', 'deal',      35, 3, '마감임박 핫딜·할인율 강조 특가 사이트',   '{"accent":"#e11d48","sort":"deal"}'::jsonb),
  ('ranking_review',   '랭킹·리뷰형',     'ranking',   40, 3, '에디터 선정 베스트 랭킹·비교 리뷰',       '{"accent":"#7c3aed"}'::jsonb),
  ('coupon_book',      '쿠폰·혜택형',     'coupon',    25, 2, '쿠폰·프로모코드 티켓형 혜택 모음',        '{"accent":"#ea580c"}'::jsonb),
  ('boutique_lookbook','감성 셀렉트샵형', 'boutique',  50, 4, '룩북·에디토리얼 감성 셀렉트샵',           '{"editorial":true}'::jsonb),
  ('review_blog',      '리뷰 블로그형',   'blog',      40, 3, '직접 써본 후기 블로그·본문 속 상품추천',   '{"columns":1}'::jsonb),
  ('price_directory',  '가격비교·카탈로그형','directory',55, 4, '다나와식 최저가 비교 카탈로그 표',        '{"accent":"#2563eb","table":true}'::jsonb)
ON CONFLICT (code) DO UPDATE SET point_cost=EXCLUDED.point_cost, complexity=EXCLUDED.complexity,
  name=EXCLUDED.name, description=EXCLUDED.description, config=EXCLUDED.config, kind=EXCLUDED.kind;

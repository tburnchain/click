-- 0017 · 회원 SaaS — 구독등급(포인트)·회원 제휴계정·빌더 템플릿·회원 사이트·포인트 원장

-- 플랜에 등급·월 포인트 추가
ALTER TABLE core.plans ADD COLUMN IF NOT EXISTS tier TEXT;
ALTER TABLE core.plans ADD COLUMN IF NOT EXISTS monthly_points INT NOT NULL DEFAULT 0;

INSERT INTO core.plans (code, display_name, price_monthly_usd, tier, monthly_points, entitlements) VALUES
  ('basic',   'Basic',   9,   'basic',   100,
   '{"networks":1,"freshness":"daily","max_sites":1,"advanced_analytics":false}'::jsonb),
  ('pro',     'Pro',     29,  'pro',     500,
   '{"networks":3,"freshness":"12h","max_sites":5,"advanced_analytics":true}'::jsonb),
  ('premium', 'Premium', 79,  'premium', 2000,
   '{"networks":"*","freshness":"hot","max_sites":20,"advanced_analytics":true}'::jsonb),
  ('vip',     'VIP',     199, 'vip',     10000,
   '{"networks":"*","freshness":"hot","max_sites":-1,"advanced_analytics":true,"priority_support":true}'::jsonb)
ON CONFLICT (code) DO UPDATE SET tier=EXCLUDED.tier, monthly_points=EXCLUDED.monthly_points,
   price_monthly_usd=EXCLUDED.price_monthly_usd, entitlements=EXCLUDED.entitlements,
   display_name=EXCLUDED.display_name;

-- 회원 계정 필드
ALTER TABLE core.users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE core.users ADD COLUMN IF NOT EXISTS display_name TEXT;

-- 포인트 원장(잔액 = Σ delta)
CREATE TABLE IF NOT EXISTS core.point_ledger (
  id         BIGSERIAL PRIMARY KEY,
  tenant_id  BIGINT NOT NULL REFERENCES core.tenants(id),
  delta      INT NOT NULL,                       -- 지급 +, 차감 -
  balance    INT NOT NULL,                        -- 트랜잭션 후 잔액(스냅샷)
  reason     TEXT NOT NULL,                        -- 'grant'|'builder_claim'|'refund'|'adjust'
  ref        TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ledger_tenant ON core.point_ledger(tenant_id, id DESC);

-- 회원 제휴 계정(암호화 자격증명 + 공개 트래킹 코드)
CREATE TABLE IF NOT EXISTS core.member_affiliate_accounts (
  id           BIGSERIAL PRIMARY KEY,
  tenant_id    BIGINT NOT NULL REFERENCES core.tenants(id),
  network_id   INT NOT NULL REFERENCES core.networks(id),
  tracking     JSONB NOT NULL DEFAULT '{}'::jsonb, -- {tag, subId, pid, nickname ...} 링크 주입용
  secret_enc   TEXT,                                -- Fernet 암호화된 API 시크릿(선택)
  status       TEXT NOT NULL DEFAULT 'active',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, network_id)
);

-- 빌더 템플릿(관리자가 포인트·복잡도 책정)
CREATE TABLE IF NOT EXISTS core.builder_templates (
  id          SERIAL PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,
  name        TEXT NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN
               ('shopping','search','general','enterprise','mixed','article')),
  point_cost  INT NOT NULL,
  complexity  INT NOT NULL DEFAULT 1,              -- 1~5
  description TEXT,
  config      JSONB NOT NULL DEFAULT '{}'::jsonb,  -- 레이아웃/색상/컬럼수 등
  is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO core.builder_templates (code, name, kind, point_cost, complexity, description, config) VALUES
  ('general_basic',  '일반형 링크 리스트',   'general',    10, 1, '심플한 상품 링크 목록',        '{"columns":1}'::jsonb),
  ('search_portal',  '검색형 포탈',          'search',     20, 2, '검색 중심 상품 포탈',          '{"search":true}'::jsonb),
  ('shopping_grid',  '쇼핑형 그리드몰',      'shopping',   30, 3, '카드 그리드 쇼핑몰 스타일',    '{"columns":3}'::jsonb),
  ('article_content','기사형 콘텐츠',        'article',    40, 3, '기사/리뷰 사이 상품 삽입',     '{"content":true}'::jsonb),
  ('mixed_hub',      '혼합형 허브',          'mixed',      60, 4, '검색+쇼핑+기사 혼합',          '{"sections":["search","grid","article"]}'::jsonb),
  ('enterprise_pro', '기업형 브랜드몰',      'enterprise', 100,5, '브랜드형 고급 레이아웃',        '{"branded":true,"columns":4}'::jsonb)
ON CONFLICT (code) DO UPDATE SET point_cost=EXCLUDED.point_cost, complexity=EXCLUDED.complexity,
  name=EXCLUDED.name, description=EXCLUDED.description, config=EXCLUDED.config;

-- 회원 사이트(클레임한 빌더 인스턴스)
CREATE TABLE IF NOT EXISTS core.member_sites (
  id                   BIGSERIAL PRIMARY KEY,
  tenant_id            BIGINT NOT NULL REFERENCES core.tenants(id),
  template_id          INT NOT NULL REFERENCES core.builder_templates(id),
  affiliate_account_id BIGINT REFERENCES core.member_affiliate_accounts(id),
  slug                 TEXT UNIQUE NOT NULL,
  title                TEXT NOT NULL,
  owner_info           JSONB NOT NULL DEFAULT '{}'::jsonb,  -- 회원 기본정보(상호·연락·소개)
  filter               JSONB NOT NULL DEFAULT '{}'::jsonb,  -- 노출 상품 필터(카테고리·네트워크·세그먼트)
  points_spent         INT NOT NULL DEFAULT 0,
  status               TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused')),
  views                BIGINT NOT NULL DEFAULT 0,
  clicks               BIGINT NOT NULL DEFAULT 0,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_member_sites_tenant ON core.member_sites(tenant_id);

-- 네트워크별 딥링크 주입 규칙(트래킹 파라미터 이름)
ALTER TABLE core.networks ADD COLUMN IF NOT EXISTS tracking_param TEXT;
UPDATE core.networks SET tracking_param = CASE code
  WHEN 'coupang_partners' THEN 'subId'
  WHEN 'amazon_assoc'     THEN 'tag'
  WHEN 'cj_affiliate'     THEN 'sid'
  WHEN 'impact'           THEN 'subId1'
  WHEN 'clickbank'        THEN 'tid'
  ELSE 'ref' END
WHERE tracking_param IS NULL;

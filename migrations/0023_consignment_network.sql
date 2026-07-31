-- 0023 · 글로벌 제휴네트워크 통합 위탁 확장 엔진
--
-- 목적: TBURN.CLICK 이 전 세계 제휴네트워크를 통합해 확보한 상품·수익 기회를
--      파트너/인플루언서에게 '위탁'하여 확장하는 구조를 데이터 모델로 확립한다.
--
-- 설계 원칙
--  1) 이벤트 소싱 — 클릭/전환을 집계 카운터가 아닌 불변 이벤트 원장으로 적재.
--     집계는 언제든 재계산 가능(어트리뷰션 모델 교체 시 과거 소급 재계산).
--  2) 귀속과 정산의 분리 — attributions(누가 얼마나 기여했나)와
--     settlements(누구에게 얼마 지급하나)를 분리해 감사 가능성 확보.
--  3) 금액은 NUMERIC — 부동소수 반올림 누적오차 금지. 배분 잔차는 애플리케이션에서
--     최대잔여법으로 처리해 합계 불일치를 0 으로 만든다.
--  4) 개인정보 비저장 — IP/UA 는 해시만 적재(원문 없음).

-- ─────────────────────────────────────────────────────────────
-- 1. 파트너 계층 — 다단계 유통 트리
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.partners (
  id                BIGSERIAL PRIMARY KEY,
  tenant_id         BIGINT NOT NULL UNIQUE REFERENCES core.tenants(id),
  parent_id         BIGINT REFERENCES core.partners(id),
  -- 물질화 경로('/1/5/12/'). 하위 트리 조회를 LIKE 로 O(index) 처리.
  path              TEXT NOT NULL DEFAULT '/',
  depth             INT  NOT NULL DEFAULT 0,
  kind              TEXT NOT NULL DEFAULT 'partner'
                    CHECK (kind IN ('house','agency','partner','influencer')),
  display_name      TEXT NOT NULL,
  tier              TEXT NOT NULL DEFAULT 'bronze'
                    CHECK (tier IN ('bronze','silver','gold','platinum','diamond')),
  -- 히스테리시스: 이 시점까지는 티어 강등 금지(등급 플래핑 방지)
  tier_locked_until DATE,
  tier_updated_at   TIMESTAMPTZ,
  status            TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','suspended','terminated')),
  meta              JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (parent_id IS NULL OR parent_id <> id)
);
CREATE INDEX IF NOT EXISTS idx_partners_parent ON core.partners(parent_id);
CREATE INDEX IF NOT EXISTS idx_partners_path   ON core.partners(path text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_partners_tier   ON core.partners(tier) WHERE status = 'active';

COMMENT ON COLUMN core.partners.path IS
  '물질화 경로 /조상id/.../자신id/ — 하위트리는 path LIKE ''/1/5/%'' 로 조회';

-- ─────────────────────────────────────────────────────────────
-- 2. 인플루언서 프로필 — 오디언스·품질 지표
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.influencer_profiles (
  partner_id       BIGINT PRIMARY KEY REFERENCES core.partners(id) ON DELETE CASCADE,
  channels         JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{platform,handle,followers,verified}]
  audience         JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {geo:{KR:0.7},age:{...},gender:{...}}
  -- 아래 점수들은 growth.scoring 이 주기적으로 재계산(0~100)
  reach_score      NUMERIC(6,2),   -- 도달(팔로워 로그스케일 정규화)
  engagement_score NUMERIC(6,2),   -- 참여 품질(베이지안 수축 적용)
  conversion_score NUMERIC(6,2),   -- 전환 기여(Wilson 하한 기반)
  fraud_score      NUMERIC(6,2),   -- 높을수록 위험
  composite_score  NUMERIC(6,2),   -- 종합(가중 기하평균)
  verified_at      TIMESTAMPTZ,
  scored_at        TIMESTAMPTZ,
  meta             JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- ─────────────────────────────────────────────────────────────
-- 3. 이벤트 원장 — 터치포인트(클릭)·전환
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.touchpoints (
  id            BIGSERIAL,
  occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  visitor_id    TEXT NOT NULL,          -- 익명 방문자 해시(쿠키리스 지문 아님, 1st-party)
  session_id    TEXT,
  partner_id    BIGINT,                 -- 귀속 대상 파트너
  site_id       BIGINT,                 -- core.member_sites
  offer_id      BIGINT,
  network_id    INT,
  channel       TEXT,                   -- 'organic'|'paid'|'social'|'email'|'direct'
  device        TEXT,
  country       CHAR(2),
  ip_hash       TEXT,                   -- 원문 미저장
  ua_hash       TEXT,
  is_bot        BOOLEAN NOT NULL DEFAULT FALSE,
  meta          JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE IF NOT EXISTS core.touchpoints_default
  PARTITION OF core.touchpoints DEFAULT;

CREATE INDEX IF NOT EXISTS idx_tp_visitor ON core.touchpoints(visitor_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_tp_partner ON core.touchpoints(partner_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_tp_offer   ON core.touchpoints(offer_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS core.conversions (
  id                BIGSERIAL,
  occurred_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  visitor_id        TEXT NOT NULL,
  network_id        INT,
  offer_id          BIGINT,
  -- 네트워크가 부여한 주문 식별자. 중복 적재 방지 키.
  order_ref         TEXT,
  gross_amount      NUMERIC(18,4),      -- 거래액(원 통화)
  currency          CHAR(3),
  commission_amount NUMERIC(18,4),      -- 네트워크가 지급하는 수수료(원 통화)
  commission_krw    NUMERIC(18,4),      -- 원화 환산(정산 기준 통화)
  status            TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','approved','rejected','paid')),
  approved_at       TIMESTAMPTZ,
  raw               JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE IF NOT EXISTS core.conversions_default
  PARTITION OF core.conversions DEFAULT;

CREATE INDEX IF NOT EXISTS idx_cv_visitor ON core.conversions(visitor_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_cv_status  ON core.conversions(status, occurred_at DESC);
-- 네트워크 주문번호 중복 방지(멱등 적재)
CREATE UNIQUE INDEX IF NOT EXISTS idx_cv_order
  ON core.conversions(network_id, order_ref, occurred_at)
  WHERE order_ref IS NOT NULL;

-- ─────────────────────────────────────────────────────────────
-- 4. 어트리뷰션 — 전환 1건이 여러 터치포인트에 분배된 결과
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.attributions (
  id               BIGSERIAL PRIMARY KEY,
  conversion_id    BIGINT NOT NULL,
  conversion_at    TIMESTAMPTZ NOT NULL,
  touchpoint_id    BIGINT,
  partner_id       BIGINT REFERENCES core.partners(id),
  model            TEXT NOT NULL,        -- 'last_click'|'time_decay'|'position'|'markov'|'shapley'
  -- 기여 가중치. 한 전환의 같은 모델 내 합계 = 1
  weight           NUMERIC(18,12) NOT NULL CHECK (weight >= 0 AND weight <= 1),
  credited_krw     NUMERIC(18,4) NOT NULL DEFAULT 0,
  computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (conversion_id, touchpoint_id, model)
);
CREATE INDEX IF NOT EXISTS idx_attr_partner ON core.attributions(partner_id, conversion_at DESC);
CREATE INDEX IF NOT EXISTS idx_attr_conv    ON core.attributions(conversion_id);

-- ─────────────────────────────────────────────────────────────
-- 5. 위탁 계약 — 수익 배분 조건
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.consignment_contracts (
  id              BIGSERIAL PRIMARY KEY,
  partner_id      BIGINT NOT NULL REFERENCES core.partners(id),
  -- 적용 범위(NULL = 전체). {"network_ids":[1,2],"categories":["뷰티"],"offer_types":["physical_product"]}
  scope           JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- 파트너 자신의 몫(귀속 수수료 대비 비율 0~1)
  revenue_share   NUMERIC(6,5) NOT NULL CHECK (revenue_share >= 0 AND revenue_share <= 1),
  -- 상위 파트너 오버라이드(하위 실적의 일정%를 상위가 받음). 단계별 배열 [0.05,0.02]
  override_rates  NUMERIC(6,5)[] NOT NULL DEFAULT '{}',
  -- 지급 보류(반품·취소 대비). 비율과 보류일수.
  holdback_rate   NUMERIC(6,5) NOT NULL DEFAULT 0 CHECK (holdback_rate >= 0 AND holdback_rate < 1),
  holdback_days   INT NOT NULL DEFAULT 30,
  min_payout_krw  NUMERIC(18,4) NOT NULL DEFAULT 10000,
  priority        INT NOT NULL DEFAULT 100,   -- 낮을수록 우선(구체적 계약 우선)
  effective_from  DATE NOT NULL DEFAULT CURRENT_DATE,
  effective_to    DATE,
  status          TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('draft','active','suspended','expired')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (effective_to IS NULL OR effective_to >= effective_from)
);
CREATE INDEX IF NOT EXISTS idx_contract_partner
  ON core.consignment_contracts(partner_id, priority) WHERE status = 'active';

-- ─────────────────────────────────────────────────────────────
-- 6. 정산 — 기간별 지급 원장
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.settlements (
  id             BIGSERIAL PRIMARY KEY,
  partner_id     BIGINT NOT NULL REFERENCES core.partners(id),
  period_start   DATE NOT NULL,
  period_end     DATE NOT NULL,
  gross_krw      NUMERIC(18,4) NOT NULL DEFAULT 0,  -- 귀속 수수료 합
  share_krw      NUMERIC(18,4) NOT NULL DEFAULT 0,  -- 계약 배분 후 파트너 몫
  override_krw   NUMERIC(18,4) NOT NULL DEFAULT 0,  -- 하위 실적 오버라이드 수취분
  holdback_krw   NUMERIC(18,4) NOT NULL DEFAULT 0,  -- 보류액
  adjust_krw     NUMERIC(18,4) NOT NULL DEFAULT 0,  -- 수동 조정(반품·페널티)
  payable_krw    NUMERIC(18,4) NOT NULL DEFAULT 0,  -- 실지급액
  status         TEXT NOT NULL DEFAULT 'draft'
                 CHECK (status IN ('draft','confirmed','paid','void')),
  computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  paid_at        TIMESTAMPTZ,
  UNIQUE (partner_id, period_start, period_end)
);
CREATE INDEX IF NOT EXISTS idx_settle_partner ON core.settlements(partner_id, period_end DESC);

CREATE TABLE IF NOT EXISTS core.settlement_lines (
  id             BIGSERIAL PRIMARY KEY,
  settlement_id  BIGINT NOT NULL REFERENCES core.settlements(id) ON DELETE CASCADE,
  kind           TEXT NOT NULL
                 CHECK (kind IN ('attribution','override','holdback','holdback_release','adjust')),
  ref_id         BIGINT,          -- attributions.id 등
  source_partner_id BIGINT REFERENCES core.partners(id),  -- 오버라이드 발생 하위
  amount_krw     NUMERIC(18,4) NOT NULL,
  memo           TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sline_settlement ON core.settlement_lines(settlement_id);

-- ─────────────────────────────────────────────────────────────
-- 7. 파트너 일별 실적 집계(재계산 가능한 캐시)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.partner_metrics_daily (
  partner_id     BIGINT NOT NULL REFERENCES core.partners(id),
  day            DATE   NOT NULL,
  clicks         BIGINT NOT NULL DEFAULT 0,
  unique_visitors BIGINT NOT NULL DEFAULT 0,
  conversions    BIGINT NOT NULL DEFAULT 0,
  revenue_krw    NUMERIC(18,4) NOT NULL DEFAULT 0,  -- 귀속 수수료
  gmv_krw        NUMERIC(18,4) NOT NULL DEFAULT 0,  -- 거래액
  -- 파생 지표: 베이지안 수축 적용값(소표본 과대평가 방지)
  epc_krw        NUMERIC(18,6),
  cvr            NUMERIC(10,8),
  cvr_lower      NUMERIC(10,8),   -- Wilson 95% 하한
  computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (partner_id, day)
);
CREATE INDEX IF NOT EXISTS idx_pmd_day ON core.partner_metrics_daily(day DESC);

-- ─────────────────────────────────────────────────────────────
-- 8. 부정 신호 — 이상탐지 결과
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.fraud_signals (
  id           BIGSERIAL PRIMARY KEY,
  partner_id   BIGINT REFERENCES core.partners(id),
  detected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  kind         TEXT NOT NULL,      -- 'click_burst'|'low_entropy'|'cvr_outlier'|'ip_concentration'|'bot_ratio'
  severity     TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info','warn','critical')),
  score        NUMERIC(8,4) NOT NULL DEFAULT 0,
  evidence     JSONB NOT NULL DEFAULT '{}'::jsonb,
  resolved_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_fraud_partner ON core.fraud_signals(partner_id, detected_at DESC);

-- ─────────────────────────────────────────────────────────────
-- 9. 하우스 파트너 시드 — 배분의 최종 귀착점(플랫폼 몫)
-- ─────────────────────────────────────────────────────────────
INSERT INTO core.tenants (name, owner_email, status)
SELECT 'TBURN.CLICK HOUSE', NULL, 'active'
WHERE NOT EXISTS (SELECT 1 FROM core.tenants WHERE name = 'TBURN.CLICK HOUSE');

INSERT INTO core.partners (tenant_id, parent_id, path, depth, kind, display_name, tier)
SELECT t.id, NULL, '/', 0, 'house', 'TBURN.CLICK HOUSE', 'diamond'
FROM core.tenants t
WHERE t.name = 'TBURN.CLICK HOUSE'
  AND NOT EXISTS (SELECT 1 FROM core.partners WHERE kind = 'house');

-- 하우스 경로 보정(자기 id 포함)
UPDATE core.partners SET path = '/' || id || '/' WHERE kind = 'house' AND path = '/';

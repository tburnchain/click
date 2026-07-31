-- 0024 · 전환 데이터 원천 — 클릭ID 왕복 + 포스트백 수신 + 리포트 임포트
--
-- 문제: 제휴 네트워크가 "전환 1건 발생"을 알려줘도, 그게 우리 파트너 중 누구의
--      실적인지 알 방법이 없다. 그래서 표준 방식은 **클릭ID 왕복**이다.
--        나가는 딥링크에 고유 토큰을 subid 로 심음
--          → 네트워크가 전환 보고 시 그 토큰을 그대로 돌려줌
--          → 토큰으로 정확한 터치포인트를 특정
--      토큰 없이는 어떤 콜백도 귀속시킬 수 없다.
--
-- 수신 경로는 셋을 모두 지원한다(네트워크마다 제공 방식이 다름)
--   push : S2S 포스트백(네트워크가 우리 URL 호출)   — 실시간, 가장 정확
--   pull : 리포트 API 폴링(우리가 조회)              — 대부분의 네트워크
--   file : CSV/스프레드시트 임포트                    — 리포트만 주는 경우

-- ─────────────────────────────────────────────────────────────
-- 1. 클릭 토큰 — 터치포인트를 외부에 노출 가능한 불투명 ID로
-- ─────────────────────────────────────────────────────────────
ALTER TABLE core.touchpoints ADD COLUMN IF NOT EXISTS click_token TEXT;

-- 파티션 테이블이라 UNIQUE 는 파티션키를 포함해야 한다. 조회는 토큰 단독 인덱스로.
CREATE INDEX IF NOT EXISTS idx_tp_click_token
  ON core.touchpoints(click_token) WHERE click_token IS NOT NULL;

COMMENT ON COLUMN core.touchpoints.click_token IS
  '외부 노출용 불투명 클릭ID. 제휴 딥링크의 subid 로 주입되어 전환 보고 시 되돌아온다.';

-- ─────────────────────────────────────────────────────────────
-- 2. 네트워크별 전환 수신 설정
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.conversion_sources (
  id              BIGSERIAL PRIMARY KEY,
  network_id      INT REFERENCES core.networks(id),
  network_code    TEXT NOT NULL UNIQUE,
  mode            TEXT NOT NULL DEFAULT 'push'
                  CHECK (mode IN ('push','pull','file')),
  -- 포스트백 서명 검증용 공유 비밀(Fernet 암호화 저장). NULL 이면 서명 미검증(IP 제한 권장)
  secret_enc      TEXT,
  -- 네트워크가 쓰는 파라미터 이름 → 우리 필드 매핑
  -- {"click_token":"subid","order_ref":"order_id","commission":"payout","currency":"cur"}
  param_map       JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- 딥링크에 클릭토큰을 심을 파라미터 이름(networks.tracking_param 보다 우선)
  click_param     TEXT,
  -- push 모드: 허용 발신 IP(비면 제한 없음). pull 모드: 리포트 엔드포인트.
  allow_ips       TEXT[] NOT NULL DEFAULT '{}',
  report_url      TEXT,
  -- 서명 방식: 'hmac_sha256'(권장) | 'none'
  signature_algo  TEXT NOT NULL DEFAULT 'hmac_sha256'
                  CHECK (signature_algo IN ('hmac_sha256','none')),
  -- 리플레이 방지 허용 시차(초)
  max_skew_sec    INT NOT NULL DEFAULT 300,
  -- 전환 기본 상태. 승인형 네트워크는 'pending', 확정 보고만 주면 'approved'
  default_status  TEXT NOT NULL DEFAULT 'pending'
                  CHECK (default_status IN ('pending','approved')),
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  last_pulled_at  TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_convsrc_active
  ON core.conversion_sources(network_code) WHERE is_active;

-- ─────────────────────────────────────────────────────────────
-- 3. 포스트백 수신 원장 — 거부된 요청까지 전부 남긴다
-- ─────────────────────────────────────────────────────────────
-- 왜 거부까지 남기는가: 네트워크가 "보냈다"고 주장하는데 전환이 없으면
-- 분쟁이 된다. 서명 불일치·중복·미매칭 사유를 증거로 보관한다.
CREATE TABLE IF NOT EXISTS core.postback_log (
  id            BIGSERIAL PRIMARY KEY,
  received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  network_code  TEXT,
  source_ip     TEXT,
  raw_query     JSONB NOT NULL DEFAULT '{}'::jsonb,
  click_token   TEXT,
  order_ref     TEXT,
  outcome       TEXT NOT NULL
                CHECK (outcome IN ('accepted','duplicate','bad_signature','unknown_network',
                                   'unmatched_click','invalid_payload','ip_rejected','stale')),
  conversion_id BIGINT,
  detail        TEXT
);
CREATE INDEX IF NOT EXISTS idx_pblog_time    ON core.postback_log(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_pblog_outcome ON core.postback_log(outcome, received_at DESC);

-- ─────────────────────────────────────────────────────────────
-- 4. 전환에 클릭토큰 연결 — 귀속 정확도의 근거
-- ─────────────────────────────────────────────────────────────
ALTER TABLE core.conversions ADD COLUMN IF NOT EXISTS click_token TEXT;
ALTER TABLE core.conversions ADD COLUMN IF NOT EXISTS source_mode TEXT;

CREATE INDEX IF NOT EXISTS idx_cv_click_token
  ON core.conversions(click_token) WHERE click_token IS NOT NULL;

COMMENT ON COLUMN core.conversions.click_token IS
  '전환을 발생시킨 클릭의 토큰. 있으면 해당 터치포인트에 확정 귀속(추정 아님).';
COMMENT ON COLUMN core.conversions.source_mode IS
  'push(실시간 포스트백) | pull(리포트 폴링) | file(임포트) | manual';

-- ─────────────────────────────────────────────────────────────
-- 5. 관리 API 키 — /growth/* 운영 경로 게이트
-- ─────────────────────────────────────────────────────────────
ALTER TABLE core.api_keys ADD COLUMN IF NOT EXISTS scopes TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE core.api_keys ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE core.api_keys ADD COLUMN IF NOT EXISTS prefix TEXT;

CREATE INDEX IF NOT EXISTS idx_apikeys_prefix ON core.api_keys(prefix) WHERE is_active;

COMMENT ON COLUMN core.api_keys.scopes IS
  '권한 범위: growth:read | growth:write | growth:settle | admin';
COMMENT ON COLUMN core.api_keys.prefix IS
  '키 앞 8자(원문 아님). 사용자가 어느 키인지 식별하기 위한 표시용.';

-- ─────────────────────────────────────────────────────────────
-- 6. 파트너 로그인 — 대시보드 접근용 세션
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.partner_sessions (
  id           BIGSERIAL PRIMARY KEY,
  partner_id   BIGINT NOT NULL REFERENCES core.partners(id) ON DELETE CASCADE,
  token_hash   TEXT NOT NULL UNIQUE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_psess_partner ON core.partner_sessions(partner_id);

-- ─────────────────────────────────────────────────────────────
-- 7. 어트리뷰션 모델 게이트 — 표본이 충분할 때만 고급 모델 사용
-- ─────────────────────────────────────────────────────────────
-- 마르코프·Shapley 는 확률 추정이므로 경로 표본이 부족하면 오히려 틀린다.
-- 통계적 검정력을 만족하는지 판단한 결과를 여기에 기록하고, 충족 시에만 켠다.
CREATE TABLE IF NOT EXISTS core.attribution_model_state (
  model            TEXT PRIMARY KEY,
  is_enabled       BOOLEAN NOT NULL DEFAULT FALSE,
  paths_observed   BIGINT NOT NULL DEFAULT 0,
  conversions_obs  BIGINT NOT NULL DEFAULT 0,
  channels_obs     INT NOT NULL DEFAULT 0,
  min_paths        BIGINT NOT NULL DEFAULT 1000,
  min_conversions  BIGINT NOT NULL DEFAULT 100,
  -- 코호트 단위로 미리 계산한 채널 가중치(개별 전환에 주입)
  channel_weights  JSONB NOT NULL DEFAULT '{}'::jsonb,
  stability        NUMERIC(6,4),   -- 부트스트랩 재표본 간 가중치 안정성 0~1
  evaluated_at     TIMESTAMPTZ,
  note             TEXT
);

INSERT INTO core.attribution_model_state (model, min_paths, min_conversions, note)
VALUES
  ('markov',  1000, 100, '흡수 마르코프 제거효과 — 경로 표본 필요'),
  ('shapley',  500,  50, '협조게임 Shapley 값 — 조합별 관측 필요')
ON CONFLICT (model) DO NOTHING;

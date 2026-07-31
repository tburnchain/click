-- 0018 · 리퍼럴(추천) 커미션 — 회원 사이트로 유입된 방문자가 가입 시 회원에게 포인트 지급

ALTER TABLE core.tenants ADD COLUMN IF NOT EXISTS referral_code TEXT;
ALTER TABLE core.tenants ADD COLUMN IF NOT EXISTS referred_by BIGINT REFERENCES core.tenants(id);

-- 기존 테넌트에 추천코드 백필(결정론적)
UPDATE core.tenants SET referral_code = upper(substr(md5(id::text || 'gamdap-ref'), 1, 8))
WHERE referral_code IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_refcode ON core.tenants(referral_code);

-- 추천 성사 원장(커미션 감사)
CREATE TABLE IF NOT EXISTS core.referrals (
  id                  BIGSERIAL PRIMARY KEY,
  referrer_tenant_id  BIGINT NOT NULL REFERENCES core.tenants(id),
  referred_tenant_id  BIGINT NOT NULL REFERENCES core.tenants(id),
  plan_code           TEXT,
  reward_points       INT NOT NULL DEFAULT 0,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (referred_tenant_id)   -- 한 가입은 1회만 커미션
);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON core.referrals(referrer_tenant_id);

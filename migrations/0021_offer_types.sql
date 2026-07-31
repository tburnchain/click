-- 0021 · 오퍼 유형 다양화 — 제휴 네트워크는 물리 상품뿐 아니라 디지털·앱·구독·리드·쿠폰도 광고한다.
-- offers.offer_type 추가 + billing_type CHECK 확장(CPI·RECURRING).

ALTER TABLE core.offers
  ADD COLUMN IF NOT EXISTS offer_type TEXT NOT NULL DEFAULT 'physical_product'
  CHECK (offer_type IN ('physical_product','digital_product','app_install',
                        'subscription','service','lead','coupon'));

-- 기존 수집분(공개데이터 물리상품)은 물리로 확정
UPDATE core.offers SET offer_type = 'physical_product' WHERE offer_type IS NULL;

-- billing_type 에 CPI(설치당)·RECURRING(구독반복) 허용
ALTER TABLE core.offers DROP CONSTRAINT IF EXISTS offers_billing_type_check;
ALTER TABLE core.offers ADD CONSTRAINT offers_billing_type_check
  CHECK (billing_type IS NULL OR billing_type IN ('CPS','CPC','CPM','CPA','CPL','CPI','RECURRING'));

CREATE INDEX IF NOT EXISTS idx_offers_offer_type ON core.offers (offer_type) WHERE is_active;

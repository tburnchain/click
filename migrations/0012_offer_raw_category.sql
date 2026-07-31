-- 0012 · 오퍼에 원본 카테고리 영속화(엔티티 해소·분류에서 활용)
-- 기존엔 raw_category 를 network_categories 학습에만 썼고 오퍼에 남기지 않았다.

ALTER TABLE core.offers ADD COLUMN IF NOT EXISTS raw_category TEXT;

-- 상품-오퍼 연결 리뷰 큐 조회용 인덱스(미연결 활성 오퍼)
CREATE INDEX IF NOT EXISTS idx_offers_unlinked
    ON core.offers(is_active) WHERE product_id IS NULL AND is_active;

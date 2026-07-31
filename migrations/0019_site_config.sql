-- 0019 · 회원 사이트 커스터마이즈 설정(수정 모드) — 히어로 문구·대표색 등

ALTER TABLE core.member_sites ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}'::jsonb;
-- config 예: {"hero_title":"...","hero_subtitle":"...","primary_color":"#ff4d4f","logo":"베스트샵"}

-- 0014 · 이력 트리거 수정(실 DB 검증에서 발견)
-- 문제: fn_offers_history 가 BEFORE INSERT 로 동작 → offers 행이 아직 없어
--       price_history FK(offer_id→offers.id) 위반.
-- 해결: updated_at 갱신은 BEFORE UPDATE, 이력 적재는 AFTER INSERT/UPDATE 로 분리.

DROP TRIGGER IF EXISTS trg_offers_history ON core.offers;

-- BEFORE UPDATE: updated_at 갱신(NEW 수정은 BEFORE 에서만 가능)
CREATE OR REPLACE FUNCTION core.fn_offers_touch() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- AFTER INSERT/UPDATE: 변경분만 이력 적재(이 시점엔 offers 행이 존재 → FK 충족)
CREATE OR REPLACE FUNCTION core.fn_offers_history() RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'INSERT')
       OR (NEW.price_amount            IS DISTINCT FROM OLD.price_amount)
       OR (NEW.commission_rate         IS DISTINCT FROM OLD.commission_rate)
       OR (NEW.commission_fixed_amount IS DISTINCT FROM OLD.commission_fixed_amount)
       OR (NEW.stock_status            IS DISTINCT FROM OLD.stock_status)
       OR (NEW.stock_quantity          IS DISTINCT FROM OLD.stock_quantity)
    THEN
        INSERT INTO core.price_history (
            offer_id, observed_at, price_amount, price_currency,
            commission_rate, commission_fixed_amount, stock_status, stock_quantity)
        VALUES (
            NEW.id, NEW.fetched_at, NEW.price_amount, NEW.price_currency,
            NEW.commission_rate, NEW.commission_fixed_amount, NEW.stock_status, NEW.stock_quantity);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_offers_touch ON core.offers;
CREATE TRIGGER trg_offers_touch
    BEFORE UPDATE ON core.offers
    FOR EACH ROW EXECUTE FUNCTION core.fn_offers_touch();

CREATE TRIGGER trg_offers_history
    AFTER INSERT OR UPDATE ON core.offers
    FOR EACH ROW EXECUTE FUNCTION core.fn_offers_history();

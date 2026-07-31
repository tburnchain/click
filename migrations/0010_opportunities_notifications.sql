-- 0010 · 기회 이벤트(변동 감지) · 알림 발송 레코드(§7 알림·이력)

-- 변동 감지 이벤트(가격 급락·수수료 인상·재고 소진 등)
CREATE TABLE IF NOT EXISTS core.opportunity_events (
    id           BIGSERIAL PRIMARY KEY,
    offer_id     BIGINT NOT NULL REFERENCES core.offers(id),
    kind         TEXT NOT NULL CHECK (kind IN
                   ('price_drop','price_up','commission_up','commission_down',
                    'stock_low','stock_out','back_in_stock')),
    severity     TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info','warn','high')),
    detail       JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {from,to,z,pct}
    detected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 동일 변동 중복 방지(오퍼+종류+감지시각 단위)
    UNIQUE (offer_id, kind, detected_at)
);
CREATE INDEX IF NOT EXISTS idx_oppo_detected ON core.opportunity_events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_oppo_offer ON core.opportunity_events(offer_id);

-- 알림 발송 레코드(실제 발송은 사용자 승인 채널로. 여기선 큐/상태만)
CREATE TABLE IF NOT EXISTS core.notifications (
    id           BIGSERIAL PRIMARY KEY,
    tenant_id    BIGINT REFERENCES core.tenants(id),
    alert_id     BIGINT REFERENCES core.alerts(id),
    event_id     BIGINT REFERENCES core.opportunity_events(id),
    channel      TEXT,                                 -- 'email'|'slack'
    status       TEXT NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued','sent','failed','skipped')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_notif_status ON core.notifications(status, created_at);

"""SaaS 엔타이틀먼트 + Stripe 웹훅 테스트(§19, M11)."""

import hashlib
import hmac

from gamdap.tenancy.entitlements import (
    feature_enabled,
    freshness_max_age_hours,
    hash_api_key,
    is_unlimited,
    network_limit_ok,
    within_quota,
)
from gamdap.tenancy.stripe_webhook import apply_stripe_event, verify_stripe_signature

PRO = {"networks": "*", "freshness": "hot", "max_alerts": -1, "api_rpm": 120,
       "export": True, "advanced_analytics": True}
FREE = {"networks": 1, "freshness": "daily", "max_alerts": 3, "api_rpm": 0,
        "export": False, "advanced_analytics": False}


# ── 엔타이틀먼트 ──
def test_is_unlimited():
    assert is_unlimited("*") and is_unlimited(-1)
    assert not is_unlimited(5)


def test_feature_gate():
    assert feature_enabled(PRO, "advanced_analytics")
    assert not feature_enabled(FREE, "advanced_analytics")
    assert feature_enabled({"export": "limited"}, "export")  # 'limited'=활성


def test_freshness_tiering():
    assert freshness_max_age_hours(PRO) == 3.0
    assert freshness_max_age_hours(FREE) == 24.0


def test_network_limit():
    assert network_limit_ok(PRO, 99)          # 무제한
    assert network_limit_ok(FREE, 1)
    assert not network_limit_ok(FREE, 2)      # free=1개 초과


def test_within_quota():
    assert within_quota(0, 0) is False        # 0=금지
    assert within_quota(5, 10) is True
    assert within_quota(10, 10) is False
    assert within_quota(999, -1) is True      # 무제한


def test_hash_api_key_stable():
    assert hash_api_key("secret") == hashlib.sha256(b"secret").hexdigest()


# ── Stripe 서명 ──
def _sig(payload: str, secret: str, t: int = 1_700_000_000) -> str:
    signed = f"{t}.{payload}"
    v1 = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={t},v1={v1}"


def test_stripe_signature_valid():
    payload = '{"type":"invoice.paid"}'
    assert verify_stripe_signature(payload, _sig(payload, "whsec"), "whsec")


def test_stripe_signature_tampered():
    payload = '{"type":"invoice.paid"}'
    header = _sig(payload, "whsec")
    assert not verify_stripe_signature('{"type":"hacked"}', header, "whsec")


def test_stripe_signature_wrong_secret():
    payload = "{}"
    assert not verify_stripe_signature(payload, _sig(payload, "a"), "b")


def test_stripe_signature_tolerance():
    payload = "{}"
    header = _sig(payload, "whsec", t=1000)
    # 현재시각 2000, tolerance 300 → 990초 차이 → 실패
    assert not verify_stripe_signature(payload, header, "whsec", timestamp=2000, tolerance=300)


# ── Stripe 이벤트 적용 ──
def test_apply_subscription_deleted():
    ev = {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_1"}}}
    up = apply_stripe_event(ev)
    assert up["status"] == "canceled"
    assert up["external_sub_id"] == "sub_1"


def test_apply_subscription_updated_uses_object_status():
    ev = {"type": "customer.subscription.updated",
          "data": {"object": {"id": "sub_2", "status": "past_due"}}}
    assert apply_stripe_event(ev)["status"] == "past_due"


def test_apply_payment_failed():
    ev = {"type": "invoice.payment_failed", "data": {"object": {"subscription": "sub_3"}}}
    assert apply_stripe_event(ev)["status"] == "past_due"


def test_apply_ignored_event():
    assert apply_stripe_event({"type": "ping", "data": {"object": {}}}) is None

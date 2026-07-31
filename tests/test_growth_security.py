"""전환 수신·인증의 보안 경계 검증.

포스트백은 인터넷에서 오는 요청이다. 서명 없이 받으면 누구나 "전환 100건"을 쏘아
지급을 유도할 수 있다. 여기서 검증하는 것은 그 경계가 실제로 닫혀 있는가다.
"""

import time
from decimal import Decimal

from gamdap.api import auth
from gamdap.growth import postback as pb


# ── 클릭 토큰 ──
def test_click_token_is_unique_and_prefixed():
    tokens = {pb.new_click_token() for _ in range(1000)}
    assert len(tokens) == 1000                    # 충돌 없음
    assert all(t.startswith("tb") for t in tokens)
    assert all(t.isalnum() for t in tokens)       # subid 안전 문자만


def test_inject_click_token_preserves_query():
    url = "https://shop.example.com/p/1?ref=abc&color=red"
    out = pb.inject_click_token(url, "subid", "tb123")
    assert "ref=abc" in out and "color=red" in out and "subid=tb123" in out


def test_inject_click_token_overwrites_existing():
    out = pb.inject_click_token("https://x.com/?subid=old", "subid", "tbNEW")
    assert "subid=tbNEW" in out and "old" not in out


def test_inject_handles_missing_inputs():
    assert pb.inject_click_token(None, "subid", "t") is None
    assert pb.inject_click_token("https://x.com", None, "t") == "https://x.com"


# ── 서명 검증 ──
def test_signature_accepts_valid_rejects_tampered():
    import hashlib
    import hmac
    secret = "shared-secret"
    payload = "amount=1000&order_id=A1"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    assert pb.verify_signature(payload=payload, signature=sig, secret=secret)
    # 금액을 조작하면 서명이 깨진다
    assert not pb.verify_signature(payload="amount=999999&order_id=A1",
                                   signature=sig, secret=secret)


def test_signature_accepts_sha256_prefix_and_case():
    import hashlib
    import hmac
    secret, payload = "s", "a=1"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    assert pb.verify_signature(payload=payload, signature=f"sha256={sig.upper()}", secret=secret)


def test_signature_rejects_missing():
    assert not pb.verify_signature(payload="a=1", signature=None, secret="s")
    assert not pb.verify_signature(payload="a=1", signature="deadbeef", secret="")


def test_signature_algo_none_bypasses():
    assert pb.verify_signature(payload="a=1", signature=None, secret="", algo="none")


def test_canonical_payload_is_order_independent():
    """파라미터 순서가 바뀌어도 같은 서명 대상이 나온다."""
    a = pb.canonical_payload({"b": 2, "a": 1, "signature": "x"})
    b = pb.canonical_payload({"a": 1, "b": 2, "sig": "y"})
    assert a == b == "a=1&b=2"


# ── 리플레이 방지 ──
def test_skew_rejects_old_timestamp():
    assert pb.check_skew(int(time.time()), 300)
    assert not pb.check_skew(int(time.time()) - 3600, 300)     # 1시간 전 = 리플레이
    assert not pb.check_skew(int(time.time()) + 3600, 300)     # 미래도 거부
    assert pb.check_skew(None, 300)                             # 미제공은 통과
    assert not pb.check_skew("not-a-number", 300)


# ── IP 허용목록 ──
def test_ip_allowlist():
    assert pb.check_ip("1.2.3.4", [])                          # 빈 목록 = 제한 없음
    assert pb.check_ip("1.2.3.4", ["1.2.3.4"])
    assert pb.check_ip("10.0.0.7", ["10.0.0.0/8"])
    assert not pb.check_ip("9.9.9.9", ["10.0.0.0/8"])
    assert not pb.check_ip(None, ["1.2.3.4"])
    assert not pb.check_ip("bad-ip", ["1.2.3.4"])


# ── 파라미터 매핑 ──
def test_map_payload_uses_explicit_map_first():
    raw = {"my_sub": "tbABC", "ord": "X1", "payout": "5000", "cur": "USD"}
    m = pb.map_payload(raw, {"click_token": "my_sub", "order_ref": "ord"})
    assert m.click_token == "tbABC" and m.order_ref == "X1"
    assert m.commission_amount == Decimal("5000") and m.currency == "USD"


def test_map_payload_falls_back_to_conventions():
    """설정이 없어도 업계 관례 이름으로 찾아낸다."""
    m = pb.map_payload({"subid": "tbZ", "transaction_id": "T9", "commission": "1,200"})
    assert m.click_token == "tbZ" and m.order_ref == "T9"
    assert m.commission_amount == Decimal("1200")     # 천단위 콤마 처리


def test_map_payload_normalizes_status():
    assert pb.map_payload({"status": "CONFIRMED"}).status == "approved"
    assert pb.map_payload({"status": "cancelled"}).status == "rejected"
    assert pb.map_payload({"status": "wait"}).status == "pending"
    assert pb.map_payload({}).status is None


def test_map_payload_rejects_negative_amount():
    assert pb.map_payload({"commission": "-500"}).commission_amount is None


def test_map_payload_is_case_insensitive():
    m = pb.map_payload({"SubID": "tbQ", "Order_ID": "O1"})
    assert m.click_token == "tbQ" and m.order_ref == "O1"


# ── API 키 ──
def test_generated_key_shape():
    raw, key_hash, prefix = auth.generate_api_key()
    assert raw.startswith("tbk_") and len(raw) > 30
    assert len(key_hash) == 64 and key_hash != raw    # 해시만 저장
    assert prefix == raw[:12] and len(prefix) == 12


def test_generated_keys_are_unique():
    keys = {auth.generate_api_key()[0] for _ in range(500)}
    assert len(keys) == 500


def test_scope_constants_cover_growth_operations():
    assert {"growth:read", "growth:write", "growth:settle", "admin"} == set(auth.SCOPES)

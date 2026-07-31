"""회원 SaaS 순수 로직 테스트 — 비밀번호·암호화·딥링크 리라이트."""

from gamdap.members.affiliate import apply_affiliate, rewrite_deeplink, tracking_value
from gamdap.members.security import decrypt, encrypt, hash_password, new_token, verify_password


# ── 비밀번호 ──
def test_password_roundtrip():
    h = hash_password("s3cret!")
    assert verify_password("s3cret!", h)
    assert not verify_password("wrong", h)


def test_password_hash_unique_salt():
    assert hash_password("x") != hash_password("x")  # 솔트 랜덤


def test_password_bad_stored():
    assert verify_password("x", "garbage") is False


# ── 자격증명 암호화 ──
def test_encrypt_roundtrip():
    secret = "AKIA-SECRET-KEY-12345"
    enc = encrypt(secret)
    assert enc != secret
    assert decrypt(enc) == secret


def test_encrypt_empty():
    assert encrypt("") == ""
    assert decrypt("") == ""


def test_token_random():
    assert new_token() != new_token()
    assert len(new_token()) > 20


# ── 딥링크 리라이트(수익화 핵심) ──
def test_rewrite_adds_param():
    url = rewrite_deeplink("https://shop.com/p/123", "tag", "myseller-20")
    assert "tag=myseller-20" in url


def test_rewrite_replaces_existing():
    url = rewrite_deeplink("https://shop.com/p?tag=old&x=1", "tag", "new")
    assert "tag=new" in url and "tag=old" not in url
    assert "x=1" in url  # 기존 파라미터 보존


def test_rewrite_preserves_path_and_query():
    url = rewrite_deeplink("https://a.com/dp/B001?ref=z", "subId", "chan1")
    assert url.startswith("https://a.com/dp/B001")
    assert "subId=chan1" in url and "ref=z" in url


def test_rewrite_noop_when_missing():
    assert rewrite_deeplink(None, "tag", "v") is None
    assert rewrite_deeplink("https://x.com", "tag", None) == "https://x.com"


def test_tracking_value_direct_and_alias():
    assert tracking_value({"tag": "abc"}, "tag") == "abc"
    assert tracking_value({"partner_tag": "xyz"}, "tag") == "xyz"       # 별칭
    assert tracking_value({"channel": "c1"}, "subId") == "c1"           # 별칭
    assert tracking_value({"only": "v"}, "unknownparam") == "v"         # 단일값 폴백


def test_apply_affiliate_injects_member_code():
    url = apply_affiliate("https://amazon.com/dp/B001", "tag", {"tag": "seller-777"})
    assert "tag=seller-777" in url


def test_apply_affiliate_no_tracking():
    assert apply_affiliate("https://x.com", "tag", None) == "https://x.com"
    assert apply_affiliate("https://x.com", "tag", {}) == "https://x.com"

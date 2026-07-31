"""쿠팡 CEA(HmacSHA256) 서명 테스트 — 메시지 조립·시각 포맷 고정."""

import hashlib
import hmac
from datetime import UTC, datetime

from gamdap.connectors.coupang import sign_request

SECRET = "test-secret-key"
ACCESS = "test-access-key"
NOW = datetime(2026, 7, 13, 9, 15, 0, tzinfo=UTC)
PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search?keyword=abc&limit=5"


def _expected_signature(dt: str) -> str:
    path, _, query = PATH.partition("?")
    message = dt + "GET" + path + query
    return hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()


def test_signed_date_format():
    _, dt = sign_request("GET", PATH, SECRET, ACCESS, now=NOW)
    assert dt == "260713T091500Z"


def test_authorization_structure():
    auth, dt = sign_request("GET", PATH, SECRET, ACCESS, now=NOW)
    assert auth.startswith("CEA algorithm=HmacSHA256, ")
    assert f"access-key={ACCESS}" in auth
    assert f"signed-date={dt}" in auth


def test_signature_matches_documented_formula():
    auth, dt = sign_request("GET", PATH, SECRET, ACCESS, now=NOW)
    expected = _expected_signature(dt)
    assert f"signature={expected}" in auth


def test_method_case_insensitive():
    a1, _ = sign_request("get", PATH, SECRET, ACCESS, now=NOW)
    a2, _ = sign_request("GET", PATH, SECRET, ACCESS, now=NOW)
    assert a1 == a2  # 내부에서 대문자화


def test_query_separated_from_path():
    # 쿼리 없는 경로도 안전해야 한다
    auth, dt = sign_request("GET", "/v1/ping", SECRET, ACCESS, now=NOW)
    expected = hmac.new(SECRET.encode(), (dt + "GET" + "/v1/ping").encode(),
                        hashlib.sha256).hexdigest()
    assert f"signature={expected}" in auth

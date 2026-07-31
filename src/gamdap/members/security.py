"""회원 인증·자격증명 보안 — 비밀번호 해시(pbkdf2)·세션토큰·자격증명 암호화(Fernet)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet

from gamdap.config import get_settings

_ITER = 200_000


# ── 비밀번호 ──
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# ── 세션 토큰 ──
def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── 자격증명 암호화(Fernet) ──
@lru_cache
def _cipher() -> Fernet:
    secret = get_settings().app_secret.encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    return _cipher().decrypt(token.encode()).decode()

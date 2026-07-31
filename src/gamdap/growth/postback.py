"""전환 데이터 수신 — 클릭ID 왕복과 포스트백 검증.

**왜 클릭ID 왕복인가**
제휴 네트워크는 "전환 1건, 수수료 5천원"만 알려준다. 그게 우리 파트너 중 누구의
실적인지는 알려주지 않는다. 그래서 나가는 딥링크에 우리가 발급한 불투명 토큰을
subid 로 심고, 네트워크가 전환 보고 시 그 토큰을 그대로 돌려주게 한다.
토큰이 되돌아오면 **추정이 아니라 확정으로** 터치포인트를 특정할 수 있다.

**신뢰 경계**
포스트백은 인터넷에서 오는 요청이다. 서명 없이 받으면 누구나 "전환 100건 발생"을
쏘아 지급을 유도할 수 있다. 따라서:
  · HMAC-SHA256 서명 검증(상수시간 비교)
  · 타임스탬프 시차 제한(리플레이 차단)
  · 발신 IP 허용목록(선택)
  · order_ref 멱등(중복 지급 차단)
거부된 요청도 사유와 함께 원장에 남긴다 — 나중에 분쟁의 증거가 된다.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

__all__ = [
    "new_click_token", "inject_click_token", "verify_signature",
    "map_payload", "PostbackResult", "OUTCOMES",
]

OUTCOMES = ("accepted", "duplicate", "bad_signature", "unknown_network",
            "unmatched_click", "invalid_payload", "ip_rejected", "stale")

# 토큰 접두사로 우리 토큰임을 식별(네트워크 로그에서 눈으로 구분 가능)
_TOKEN_PREFIX = "tb"


def new_click_token() -> str:
    """충돌 확률이 무시 가능한 불투명 클릭 토큰.

    128비트 난수 → base32 유사 문자열. 제휴 네트워크의 subid 는 길이·문자 제한이
    있는 경우가 많아(보통 50자 이내, 영숫자) 안전한 형태로 만든다.
    """
    return _TOKEN_PREFIX + secrets.token_hex(16)


def inject_click_token(url: str | None, param: str | None, token: str) -> str | None:
    """딥링크에 클릭 토큰을 심는다. 기존 쿼리는 보존한다."""
    if not url or not param or not token:
        return url
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[param] = token
    return urlunparse(parts._replace(query=urlencode(query)))


def verify_signature(*, payload: str, signature: str | None, secret: str,
                     algo: str = "hmac_sha256") -> bool:
    """HMAC 서명 검증. 상수시간 비교로 타이밍 공격을 막는다."""
    if algo == "none":
        return True
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    # 네트워크에 따라 대소문자·접두사('sha256=')가 다르다
    got = signature.strip().lower()
    if got.startswith("sha256="):
        got = got[7:]
    return hmac.compare_digest(expected, got)


def check_skew(timestamp: str | int | None, max_skew_sec: int) -> bool:
    """타임스탬프 시차 검사(리플레이 차단). 없으면 통과(네트워크가 안 보낼 수 있음)."""
    if timestamp is None or timestamp == "":
        return True
    try:
        ts = int(float(timestamp))
    except (TypeError, ValueError):
        return False
    return abs(time.time() - ts) <= max_skew_sec


def check_ip(source_ip: str | None, allow_ips: list[str]) -> bool:
    """발신 IP 허용목록. 비어 있으면 제한 없음."""
    if not allow_ips:
        return True
    if not source_ip:
        return False
    import ipaddress
    try:
        ip = ipaddress.ip_address(source_ip)
    except ValueError:
        return False
    for entry in allow_ips:
        try:
            if "/" in entry:
                if ip in ipaddress.ip_network(entry, strict=False):
                    return True
            elif ip == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def _dec(v: object) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d >= 0 else None


@dataclass
class MappedPayload:
    click_token: str | None = None
    order_ref: str | None = None
    gross_amount: Decimal | None = None
    commission_amount: Decimal | None = None
    currency: str = "KRW"
    status: str | None = None
    offer_ref: str | None = None
    timestamp: str | None = None
    signature: str | None = None


# 필드별 기본 후보 이름 — param_map 에 없으면 이 관례로 찾는다.
# 네트워크마다 이름이 제각각이라 흔한 관례를 모두 시도한다.
_DEFAULTS: dict[str, tuple[str, ...]] = {
    "click_token": ("subid", "sub_id", "sid", "click_id", "clickid", "aff_sub",
                    "tb_clickid", "u1", "sid1", "subid1"),
    "order_ref": ("order_id", "orderid", "transaction_id", "txn_id", "conversion_id",
                  "oid", "order_ref"),
    "gross_amount": ("amount", "sale_amount", "order_amount", "total", "revenue", "gmv"),
    "commission_amount": ("commission", "payout", "commission_amount", "publisher_commission",
                          "earnings"),
    "currency": ("currency", "cur", "curr", "currency_code"),
    "status": ("status", "state", "conversion_status"),
    "offer_ref": ("offer_id", "product_id", "sku", "item_id"),
    "timestamp": ("timestamp", "ts", "time", "event_time"),
    "signature": ("signature", "sign", "sig", "hmac", "checksum"),
}


def map_payload(raw: dict, param_map: dict | None = None) -> MappedPayload:
    """네트워크별 파라미터 이름을 우리 필드로 정규화.

    param_map 이 지정한 이름을 먼저 보고, 없으면 업계 관례 후보를 순서대로 찾는다.
    → 새 네트워크 추가가 '코드 수정'이 아니라 '설정 추가'로 끝난다.
    """
    param_map = param_map or {}
    lower = {str(k).lower(): v for k, v in raw.items()}

    def pick(field: str) -> object:
        explicit = param_map.get(field)
        if explicit and str(explicit).lower() in lower:
            return lower[str(explicit).lower()]
        for cand in _DEFAULTS.get(field, ()):
            if cand in lower and lower[cand] not in (None, ""):
                return lower[cand]
        return None

    cur = pick("currency")
    status_raw = pick("status")
    status = None
    if status_raw is not None:
        s = str(status_raw).strip().lower()
        if s in ("approved", "confirmed", "paid", "completed", "valid", "1", "true"):
            status = "approved"
        elif s in ("rejected", "declined", "cancelled", "canceled", "invalid", "0", "false"):
            status = "rejected"
        else:
            status = "pending"

    token = pick("click_token")
    return MappedPayload(
        click_token=str(token).strip() if token else None,
        order_ref=str(pick("order_ref")).strip() if pick("order_ref") else None,
        gross_amount=_dec(pick("gross_amount")),
        commission_amount=_dec(pick("commission_amount")),
        currency=(str(cur).strip().upper()[:3] if cur else "KRW"),
        status=status,
        offer_ref=str(pick("offer_ref")).strip() if pick("offer_ref") else None,
        timestamp=str(pick("timestamp")) if pick("timestamp") else None,
        signature=str(pick("signature")) if pick("signature") else None,
    )


def canonical_payload(raw: dict, *, exclude: tuple[str, ...] = ("signature", "sign", "sig",
                                                               "hmac", "checksum")) -> str:
    """서명 대상 문자열 — 키 정렬 후 k=v&… 형태.

    서명 필드 자신은 제외한다. 정렬하지 않으면 파라미터 순서가 바뀔 때 서명이 깨진다.
    """
    items = sorted((str(k), str(v)) for k, v in raw.items()
                   if str(k).lower() not in exclude)
    return "&".join(f"{k}={v}" for k, v in items)


@dataclass
class PostbackResult:
    outcome: str
    conversion_id: int | None = None
    detail: str | None = None
    partner_id: int | None = None

    @property
    def accepted(self) -> bool:
        return self.outcome == "accepted"


def utc_now() -> datetime:
    return datetime.now(UTC)

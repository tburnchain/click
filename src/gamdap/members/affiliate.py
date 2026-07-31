"""딥링크 리라이터 — 상품 URL에 회원의 제휴 트래킹 코드를 주입(수익 귀속).

방문자가 회원 사이트의 링크를 클릭하면 그 회원의 제휴코드가 붙어 → 회원의 수익이 된다.
네트워크별 트래킹 파라미터 이름은 core.networks.tracking_param 에서 온다.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def rewrite_deeplink(url: str | None, param: str | None, value: str | None) -> str | None:
    """URL 쿼리스트링에 {param}={value} 주입/치환. 순수 함수."""
    if not url or not param or not value:
        return url
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[param] = value
    return urlunparse(parts._replace(query=urlencode(query)))


def tracking_value(tracking: dict, param: str | None) -> str | None:
    """회원 트래킹 dict 에서 해당 param 값 선택. 별칭 지원(subId1↔subId 등)."""
    if not tracking or not param:
        return None
    if param in tracking and tracking[param]:
        return str(tracking[param])
    # 흔한 별칭 매핑
    aliases = {
        "subId": ["subid", "sub_id", "channel"],
        "subId1": ["subId", "subid", "sub_id"],
        "tag": ["partner_tag", "associate_tag"],
        "sid": ["pid", "website_id", "sid"],
        "tid": ["nickname", "hopid", "tid"],
    }
    for alt in aliases.get(param, []):
        if alt in tracking and tracking[alt]:
            return str(tracking[alt])
    # 단일 값만 있으면 그것을 사용
    non_empty = [v for v in tracking.values() if v]
    return str(non_empty[0]) if len(non_empty) == 1 else None


def apply_affiliate(landing_url: str | None, tracking_param: str | None,
                    tracking: dict | None) -> str | None:
    """오퍼 랜딩 URL에 회원 트래킹 적용. 트래킹 없으면 원본 반환."""
    if not tracking:
        return landing_url
    val = tracking_value(tracking, tracking_param)
    return rewrite_deeplink(landing_url, tracking_param, val)

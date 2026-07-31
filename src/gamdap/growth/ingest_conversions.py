"""전환 수신 오케스트레이션 — push(포스트백) · pull(리포트) · file(임포트).

세 경로 모두 같은 종착점(core.conversions)으로 들어오고, 클릭 토큰이 있으면
해당 터치포인트에 **확정 귀속**된다(경로 추정을 건너뛴다).

거부 사유는 전부 postback_log 에 남는다. "보냈는데 왜 정산에 없느냐"는 분쟁이
반드시 생기고, 그때 필요한 것은 로그다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from psycopg import Connection

from gamdap.growth import postback as pb
from gamdap.logging import get_logger
from gamdap.members.security import decrypt, encrypt

log = get_logger("growth.conversions")


# ─────────────────────────────────────────────────────────────
# 설정 관리
# ─────────────────────────────────────────────────────────────
def upsert_source(conn: Connection, *, network_code: str, mode: str = "push",
                  secret: str | None = None, param_map: dict | None = None,
                  click_param: str | None = None, allow_ips: list[str] | None = None,
                  report_url: str | None = None, signature_algo: str = "hmac_sha256",
                  default_status: str = "pending", network_id: int | None = None) -> int:
    """전환 원천 등록/갱신. 비밀은 Fernet 암호화해 저장한다(원문 미보관)."""
    secret_enc = encrypt(secret) if secret else None
    row = conn.execute(
        "INSERT INTO core.conversion_sources (network_id, network_code, mode, secret_enc, "
        "param_map, click_param, allow_ips, report_url, signature_algo, default_status) "
        "VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s) "
        "ON CONFLICT (network_code) DO UPDATE SET mode=EXCLUDED.mode, "
        "  secret_enc=COALESCE(EXCLUDED.secret_enc, core.conversion_sources.secret_enc), "
        "  param_map=EXCLUDED.param_map, click_param=EXCLUDED.click_param, "
        "  allow_ips=EXCLUDED.allow_ips, report_url=EXCLUDED.report_url, "
        "  signature_algo=EXCLUDED.signature_algo, default_status=EXCLUDED.default_status, "
        "  is_active=TRUE RETURNING id",
        (network_id, network_code, mode, secret_enc,
         json.dumps(param_map or {}, ensure_ascii=False), click_param,
         allow_ips or [], report_url, signature_algo, default_status)).fetchone()
    return row["id"]


def _load_source(conn: Connection, network_code: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM core.conversion_sources WHERE network_code=%s AND is_active",
        (network_code,)).fetchone()
    return dict(row) if row else None


def _log(conn: Connection, *, network_code: str | None, source_ip: str | None,
         raw: dict, mapped: pb.MappedPayload | None, outcome: str,
         conversion_id: int | None = None, detail: str | None = None) -> None:
    conn.execute(
        "INSERT INTO core.postback_log (network_code, source_ip, raw_query, click_token, "
        "order_ref, outcome, conversion_id, detail) VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s,%s)",
        (network_code, source_ip, json.dumps(raw, ensure_ascii=False, default=str),
         mapped.click_token if mapped else None,
         mapped.order_ref if mapped else None, outcome, conversion_id, detail))


# ─────────────────────────────────────────────────────────────
# push — S2S 포스트백
# ─────────────────────────────────────────────────────────────
def handle_postback(conn: Connection, *, network_code: str, raw: dict,
                    source_ip: str | None = None) -> pb.PostbackResult:
    """포스트백 1건 처리. 모든 거부 경로가 로그를 남긴다."""
    src = _load_source(conn, network_code)
    if not src:
        _log(conn, network_code=network_code, source_ip=source_ip, raw=raw, mapped=None,
             outcome="unknown_network", detail="등록되지 않은 네트워크")
        return pb.PostbackResult("unknown_network", detail="등록되지 않은 네트워크")

    if not pb.check_ip(source_ip, list(src.get("allow_ips") or [])):
        _log(conn, network_code=network_code, source_ip=source_ip, raw=raw, mapped=None,
             outcome="ip_rejected", detail=f"허용되지 않은 발신 IP: {source_ip}")
        return pb.PostbackResult("ip_rejected", detail="허용되지 않은 발신 IP")

    mapped = pb.map_payload(raw, src.get("param_map"))

    algo = src.get("signature_algo") or "hmac_sha256"
    if algo != "none":
        secret = decrypt(src.get("secret_enc") or "") if src.get("secret_enc") else ""
        ok = pb.verify_signature(payload=pb.canonical_payload(raw),
                                 signature=mapped.signature, secret=secret, algo=algo)
        if not ok:
            _log(conn, network_code=network_code, source_ip=source_ip, raw=raw, mapped=mapped,
                 outcome="bad_signature", detail="HMAC 서명 불일치")
            return pb.PostbackResult("bad_signature", detail="서명 검증 실패")

    if not pb.check_skew(mapped.timestamp, int(src.get("max_skew_sec") or 300)):
        _log(conn, network_code=network_code, source_ip=source_ip, raw=raw, mapped=mapped,
             outcome="stale", detail="타임스탬프 시차 초과(리플레이 의심)")
        return pb.PostbackResult("stale", detail="타임스탬프 시차 초과")

    if not mapped.order_ref and not mapped.click_token:
        _log(conn, network_code=network_code, source_ip=source_ip, raw=raw, mapped=mapped,
             outcome="invalid_payload", detail="order_ref·click_token 둘 다 없음 — 식별 불가")
        return pb.PostbackResult("invalid_payload", detail="식별자 없음")

    return _ingest(conn, src=src, mapped=mapped, raw=raw, source_ip=source_ip, mode="push")


def _ingest(conn: Connection, *, src: dict, mapped: pb.MappedPayload, raw: dict,
            source_ip: str | None, mode: str) -> pb.PostbackResult:
    """검증을 통과한 전환을 적재. 클릭 토큰이 있으면 확정 귀속한다."""
    network_id = src.get("network_id")

    # 멱등: 같은 (네트워크, 주문번호) 는 한 번만
    if mapped.order_ref:
        dup = conn.execute(
            "SELECT id FROM core.conversions WHERE network_id IS NOT DISTINCT FROM %s "
            "AND order_ref=%s LIMIT 1", (network_id, mapped.order_ref)).fetchone()
        if dup:
            _log(conn, network_code=src["network_code"], source_ip=source_ip, raw=raw,
                 mapped=mapped, outcome="duplicate", conversion_id=dup["id"],
                 detail="이미 적재된 주문")
            return pb.PostbackResult("duplicate", conversion_id=dup["id"],
                                     detail="이미 적재된 주문")

    # 클릭 토큰 → 터치포인트 특정(확정 귀속의 근거)
    visitor_id = None
    partner_id = None
    offer_id = None
    if mapped.click_token:
        tp = conn.execute(
            "SELECT visitor_id, partner_id, offer_id FROM core.touchpoints "
            "WHERE click_token=%s ORDER BY occurred_at DESC LIMIT 1",
            (mapped.click_token,)).fetchone()
        if tp:
            visitor_id = tp["visitor_id"]
            partner_id = tp["partner_id"]
            offer_id = tp["offer_id"]
        else:
            _log(conn, network_code=src["network_code"], source_ip=source_ip, raw=raw,
                 mapped=mapped, outcome="unmatched_click",
                 detail=f"클릭 토큰 미매칭: {mapped.click_token}")
            return pb.PostbackResult("unmatched_click",
                                     detail="클릭 토큰에 해당하는 터치포인트 없음")

    if not visitor_id:
        # 토큰 없이 주문번호만 온 경우 — 적재는 하되 귀속은 불가(수동 매칭 대상)
        visitor_id = f"unmatched:{mapped.order_ref}"

    commission = mapped.commission_amount
    # 원화 환산: 통화가 KRW 면 그대로, 아니면 최신 환율로(없으면 NULL → 정산 제외)
    commission_krw = commission if mapped.currency == "KRW" else _to_krw(
        conn, commission, mapped.currency)

    status = mapped.status or src.get("default_status") or "pending"
    row = conn.execute(
        "INSERT INTO core.conversions (visitor_id, network_id, offer_id, order_ref, "
        "gross_amount, currency, commission_amount, commission_krw, status, click_token, "
        "source_mode, raw, approved_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING id",
        (visitor_id, network_id, offer_id, mapped.order_ref, mapped.gross_amount,
         mapped.currency, commission, commission_krw, status, mapped.click_token, mode,
         json.dumps(raw, ensure_ascii=False, default=str),
         datetime.now(UTC) if status == "approved" else None)).fetchone()

    _log(conn, network_code=src["network_code"], source_ip=source_ip, raw=raw, mapped=mapped,
         outcome="accepted", conversion_id=row["id"])
    log.info("conversion.ingested", network=src["network_code"], mode=mode,
             conversion_id=row["id"], matched=bool(partner_id))
    return pb.PostbackResult("accepted", conversion_id=row["id"], partner_id=partner_id)


def _to_krw(conn: Connection, amount: Decimal | None, currency: str) -> Decimal | None:
    if amount is None:
        return None
    row = conn.execute(
        "SELECT rate FROM core.exchange_rates WHERE base_currency=%s AND quote_currency='KRW' "
        "ORDER BY as_of DESC LIMIT 1", (currency,)).fetchone()
    if not row or not row["rate"]:
        return None
    return (amount * Decimal(str(row["rate"]))).quantize(Decimal("0.0001"))


# ─────────────────────────────────────────────────────────────
# file — 리포트 임포트(대부분의 네트워크가 이 경로)
# ─────────────────────────────────────────────────────────────
def import_rows(conn: Connection, *, network_code: str,
                rows: Iterable[dict], mode: str = "file") -> dict:
    """리포트 행들을 전환으로 적재. 각 행은 포스트백과 동일하게 매핑된다.

    서명 검증은 하지 않는다(파일은 운영자가 올린 것). 대신 멱등과 매칭은 동일하다.
    """
    src = _load_source(conn, network_code)
    if not src:
        raise ValueError(f"등록되지 않은 전환 원천: {network_code}")

    tally = {"accepted": 0, "duplicate": 0, "unmatched_click": 0, "invalid_payload": 0}
    for raw in rows:
        mapped = pb.map_payload(raw, src.get("param_map"))
        if not mapped.order_ref and not mapped.click_token:
            tally["invalid_payload"] += 1
            _log(conn, network_code=network_code, source_ip=None, raw=raw, mapped=mapped,
                 outcome="invalid_payload", detail="식별자 없음")
            continue
        result = _ingest(conn, src=src, mapped=mapped, raw=raw, source_ip=None, mode=mode)
        tally[result.outcome] = tally.get(result.outcome, 0) + 1
    return tally


# ─────────────────────────────────────────────────────────────
# pull — 리포트 API 폴링
# ─────────────────────────────────────────────────────────────
def pull_report(conn: Connection, *, network_code: str, fetcher) -> dict:
    """네트워크 리포트 API 를 호출해 전환을 적재.

    fetcher 는 (report_url, since) → Iterable[dict] 인 호출 가능 객체.
    네트워크별 인증/페이징은 fetcher 가 담당한다(여기선 적재만).
    """
    src = _load_source(conn, network_code)
    if not src:
        raise ValueError(f"등록되지 않은 전환 원천: {network_code}")
    since = src.get("last_pulled_at")
    rows = list(fetcher(src.get("report_url"), since))
    tally = import_rows(conn, network_code=network_code, rows=rows, mode="pull")
    conn.execute("UPDATE core.conversion_sources SET last_pulled_at=now() WHERE id=%s",
                 (src["id"],))
    tally["fetched"] = len(rows)
    return tally


# ─────────────────────────────────────────────────────────────
# 확정 귀속 — 클릭 토큰이 있는 전환은 경로 추정 없이 100% 귀속
# ─────────────────────────────────────────────────────────────
def attribute_direct(conn: Connection, *, model: str = "direct_click", limit: int = 1000) -> int:
    """클릭 토큰으로 매칭된 전환을 해당 터치포인트에 100% 귀속.

    멀티터치 모델과 별개 모델명으로 저장하므로 공존한다. 정산은 어느 모델을
    기준으로 할지 선택할 수 있다(기본은 멀티터치, 감사 시 확정 귀속 대조).
    """
    rows = conn.execute(
        "SELECT c.id, c.occurred_at, c.click_token, COALESCE(c.commission_krw,0) krw "
        "FROM core.conversions c "
        "WHERE c.click_token IS NOT NULL "
        "  AND NOT EXISTS (SELECT 1 FROM core.attributions a "
        "                  WHERE a.conversion_id=c.id AND a.model=%s) "
        "ORDER BY c.occurred_at DESC LIMIT %s", (model, limit)).fetchall()
    n = 0
    for cv in rows:
        tp = conn.execute(
            "SELECT id, partner_id FROM core.touchpoints WHERE click_token=%s "
            "ORDER BY occurred_at DESC LIMIT 1", (cv["click_token"],)).fetchone()
        if not tp:
            continue
        conn.execute(
            "INSERT INTO core.attributions (conversion_id, conversion_at, touchpoint_id, "
            "partner_id, model, weight, credited_krw) VALUES (%s,%s,%s,%s,%s,1,%s) "
            "ON CONFLICT (conversion_id, touchpoint_id, model) DO UPDATE "
            "SET credited_krw=EXCLUDED.credited_krw, computed_at=now()",
            (cv["id"], cv["occurred_at"], tp["id"], tp["partner_id"], model, cv["krw"]))
        n += 1
    return n

"""전환 수신 엔드투엔드 검증 — 클릭ID 왕복이 실제로 성립하는지 확인한다.

시나리오
  1) 파트너 사이트에서 클릭 → 클릭토큰 발급, 딥링크에 subid 로 주입
  2) 네트워크가 그 토큰을 되돌려주며 전환 포스트백 전송(서명 포함)
  3) 토큰으로 터치포인트를 특정 → 확정 귀속
  4) 위조 시도(서명 조작·리플레이·중복)가 모두 차단되는지 확인
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
for k, v in {"GAMDAP_DB_HOST": "127.0.0.1", "GAMDAP_DB_PORT": "5433", "GAMDAP_DB_NAME": "gamdap",
             "GAMDAP_DB_USER": "postgres", "GAMDAP_DB_PASSWORD": "x",
             "PYTHONIOENCODING": "utf-8", "PGCLIENTENCODING": "UTF8"}.items():
    os.environ.setdefault(k, v)

from gamdap.db import transaction  # noqa: E402
from gamdap.growth import ingest_conversions as ic  # noqa: E402
from gamdap.growth import postback as pb  # noqa: E402
from gamdap.growth import service as gs  # noqa: E402

NETWORK = "demo_network"
SECRET = "demo-shared-secret-not-a-real-key"


def signed(params: dict) -> dict:
    """네트워크가 보내는 형태로 서명을 붙인다."""
    payload = pb.canonical_payload(params)
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {**params, "signature": sig}


def main() -> int:
    ok = True
    with transaction() as conn:
        ic.upsert_source(conn, network_code=NETWORK, mode="push", secret=SECRET,
                         param_map={"click_token": "subid", "order_ref": "order_id",
                                    "commission_amount": "payout"},
                         click_param="subid", default_status="approved")
        print(f"■ 전환 원천 등록: {NETWORK} (서명 검증 ON)")

        # 1) 클릭 → 토큰 발급
        house = gs.house_partner_id(conn)
        p = conn.execute("SELECT id FROM core.partners WHERE kind<>'house' ORDER BY id LIMIT 1"
                         ).fetchone()
        partner_id = p["id"] if p else house
        visitor = f"pbdemo-{int(time.time())}"
        token = pb.new_click_token()
        tp_id = gs.record_touchpoint(conn, visitor_id=visitor, partner_id=partner_id,
                                     channel="social", click_token=token)
        link = pb.inject_click_token("https://shop.example.com/p/9?ref=x", "subid", token)
        print(f"■ 클릭 적재 (터치포인트 {tp_id})")
        print(f"   나가는 링크: {link}")

    # 2) 정상 포스트백
    params = {"subid": token, "order_id": f"ORD-{int(time.time())}",
              "payout": "12000", "currency": "KRW", "timestamp": str(int(time.time()))}
    with transaction() as conn:
        r = ic.handle_postback(conn, network_code=NETWORK, raw=signed(params),
                               source_ip="203.0.113.9")
    print(f"■ 정상 포스트백 → {r.outcome} (전환 {r.conversion_id}, 파트너 {r.partner_id})")
    ok &= r.accepted and r.partner_id == partner_id

    # 3) 확정 귀속
    with transaction() as conn:
        n = ic.attribute_direct(conn)
        row = conn.execute(
            "SELECT a.partner_id, a.weight, a.credited_krw FROM core.attributions a "
            "WHERE a.conversion_id=%s AND a.model='direct_click'", (r.conversion_id,)).fetchone()
    print(f"■ 확정 귀속 {n}건 → 파트너 {row['partner_id']} 가중 {float(row['weight']):.0%} "
          f"· {Decimal(str(row['credited_krw'])):,} KRW")
    ok &= row is not None and float(row["weight"]) == 1.0

    print("\n── 공격 차단 검증 ──")
    # 위조 1: 금액만 바꿔치기(서명 그대로)
    tampered = {**signed(params), "payout": "9999999"}
    with transaction() as conn:
        r2 = ic.handle_postback(conn, network_code=NETWORK, raw=tampered, source_ip="1.2.3.4")
    print(f"   금액 조작       → {r2.outcome} {'✔ 차단' if r2.outcome == 'bad_signature' else '✘ 통과됨'}")
    ok &= r2.outcome == "bad_signature"

    # 위조 2: 리플레이(같은 주문 재전송)
    with transaction() as conn:
        r3 = ic.handle_postback(conn, network_code=NETWORK, raw=signed(params),
                                source_ip="203.0.113.9")
    print(f"   중복 재전송     → {r3.outcome} {'✔ 차단' if r3.outcome == 'duplicate' else '✘ 통과됨'}")
    ok &= r3.outcome == "duplicate"

    # 위조 3: 오래된 타임스탬프
    old = {"subid": token, "order_id": "OLD-1", "payout": "500",
           "timestamp": str(int(time.time()) - 7200)}
    with transaction() as conn:
        r4 = ic.handle_postback(conn, network_code=NETWORK, raw=signed(old), source_ip=None)
    print(f"   오래된 타임스탬프 → {r4.outcome} {'✔ 차단' if r4.outcome == 'stale' else '✘ 통과됨'}")
    ok &= r4.outcome == "stale"

    # 위조 4: 없는 클릭 토큰
    fake = {"subid": "tbFAKE0000", "order_id": "FAKE-1", "payout": "88888",
            "timestamp": str(int(time.time()))}
    with transaction() as conn:
        r5 = ic.handle_postback(conn, network_code=NETWORK, raw=signed(fake), source_ip=None)
    print(f"   위조 클릭ID     → {r5.outcome} {'✔ 차단' if r5.outcome == 'unmatched_click' else '✘ 통과됨'}")
    ok &= r5.outcome == "unmatched_click"

    # 위조 5: 미등록 네트워크
    with transaction() as conn:
        r6 = ic.handle_postback(conn, network_code="not_registered", raw=params, source_ip=None)
    print(f"   미등록 네트워크  → {r6.outcome} {'✔ 차단' if r6.outcome == 'unknown_network' else '✘ 통과됨'}")
    ok &= r6.outcome == "unknown_network"

    with transaction() as conn:
        logs = conn.execute(
            "SELECT outcome, count(*) n FROM core.postback_log "
            "WHERE network_code IN (%s,%s) GROUP BY 1 ORDER BY 2 DESC",
            (NETWORK, "not_registered")).fetchall()
    print("\n■ 수신 원장(분쟁 증거):", ", ".join(f"{r['outcome']}={r['n']}" for r in logs))
    print(f"\n{'✔ 전체 통과' if ok else '✘ 실패 — 위 항목 확인'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

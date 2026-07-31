"""위탁 확장 엔진 엔드투엔드 검증 — 실제 DB에 시나리오를 흘려 불변식을 확인한다.

시나리오: 에이전시(A) 아래 파트너(P1,P2), 인플루언서(I1).
방문자가 여러 파트너 사이트를 거쳐 구매 → 귀속 배분 → 스코어링 → 정산까지 실행하고
'귀속 수수료 합 = 배분 합' 이 정확히 성립하는지 검증한다.

멱등: 재실행해도 중복 적재되지 않는다(테스트 파트너는 고정 이름으로 재사용).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
for k, v in {"GAMDAP_DB_HOST": "127.0.0.1", "GAMDAP_DB_PORT": "5433", "GAMDAP_DB_NAME": "gamdap",
             "GAMDAP_DB_USER": "postgres", "GAMDAP_DB_PASSWORD": "x",
             "PYTHONIOENCODING": "utf-8", "PGCLIENTENCODING": "UTF8"}.items():
    os.environ.setdefault(k, v)

from gamdap.db import transaction  # noqa: E402
from gamdap.growth import service as gs  # noqa: E402

TENANTS = [("DEMO 에이전시", "agency", None), ("DEMO 파트너1", "partner", 0),
           ("DEMO 파트너2", "partner", 0), ("DEMO 인플루언서1", "influencer", 1)]


def _ensure_tenant(conn, name: str) -> int:
    row = conn.execute("SELECT id FROM core.tenants WHERE name=%s", (name,)).fetchone()
    if row:
        return row["id"]
    return conn.execute("INSERT INTO core.tenants (name, status) VALUES (%s,'active') RETURNING id",
                        (name,)).fetchone()["id"]


def main() -> int:
    now = datetime.now(UTC)
    with transaction() as conn:
        house = gs.house_partner_id(conn)
        # 파트너 트리 구성
        ids: list[int] = []
        for name, kind, parent_idx in TENANTS:
            tid = _ensure_tenant(conn, name)
            parent = ids[parent_idx] if parent_idx is not None else house
            p = gs.register_partner(conn, tenant_id=tid, display_name=name,
                                    parent_id=parent, kind=kind)
            ids.append(p["id"])
        agency, p1, p2, inf1 = ids
        print(f"■ 파트너 트리: 하우스({house}) → 에이전시({agency}) → [{p1}, {p2}] → 인플루언서({inf1})")

        # 방문자 여정: 인플루언서 발견 → 파트너1 비교 → 파트너2 구매
        visitor = f"demo-visitor-{now:%Y%m%d}"
        conn.execute("DELETE FROM core.attributions WHERE conversion_id IN "
                     "(SELECT id FROM core.conversions WHERE visitor_id=%s)", (visitor,))
        conn.execute("DELETE FROM core.conversions WHERE visitor_id=%s", (visitor,))
        conn.execute("DELETE FROM core.touchpoints WHERE visitor_id=%s", (visitor,))

        for i, (pid, ch, days_ago) in enumerate([(inf1, "social", 5), (p1, "organic", 2),
                                                 (p2, "paid", 0)]):
            tp = gs.record_touchpoint(conn, visitor_id=visitor, partner_id=pid,
                                      channel=ch, country="KR", ip=f"10.0.0.{i}",
                                      user_agent="demo-agent")
            conn.execute("UPDATE core.touchpoints SET occurred_at=%s WHERE id=%s",
                         (now - timedelta(days=days_ago), tp))
        print("■ 터치포인트 3건 적재(인플루언서 발견 → 파트너1 비교 → 파트너2 구매)")

        commission = Decimal("100000.0000")
        cid = gs.record_conversion(conn, visitor_id=visitor, network_id=None,
                                   order_ref=f"DEMO-{now:%Y%m%d}", gross_amount=Decimal("1000000"),
                                   currency="KRW", commission_amount=commission,
                                   commission_krw=commission, status="approved")
        print(f"■ 전환 1건: 수수료 {commission:,} KRW (전환ID {cid})")

    # 어트리뷰션
    with transaction() as conn:
        rep = gs.run_attribution(conn, model="time_decay")
    print(f"■ 어트리뷰션: 전환 {rep['conversions']}건 · 배분 {rep['credited_krw']:,} KRW")

    with transaction() as conn:
        rows = conn.execute(
            "SELECT a.partner_id, p.display_name, a.weight, a.credited_krw "
            "FROM core.attributions a JOIN core.partners p ON p.id=a.partner_id "
            "WHERE a.conversion_id=%s AND a.model='time_decay' ORDER BY a.credited_krw DESC",
            (cid,)).fetchall()
        print("   기여 배분:")
        total_credited = Decimal("0")
        for r in rows:
            print(f"     · {r['display_name']:16} 가중 {float(r['weight']):6.2%} → "
                  f"{Decimal(str(r['credited_krw'])):>12,} KRW")
            total_credited += Decimal(str(r["credited_krw"]))
        ok = total_credited == commission
        print(f"   ✔ 불변식 검증: 배분합 {total_credited:,} == 수수료 {commission:,} → "
              f"{'통과' if ok else '실패'}")
        if not ok:
            return 1

    # 집계·스코어링
    day = (now - timedelta(days=0)).date()
    with transaction() as conn:
        n = gs.refresh_metrics(conn, day=day)
    with transaction() as conn:
        scored = gs.rescore_partners(conn)
    print(f"■ 집계 {n}개 파트너 · 스코어링 {scored}명")

    # 정산
    with transaction() as conn:
        result = gs.build_settlement(conn, period_start=day - timedelta(days=30),
                                     period_end=day)
    print(f"■ 정산: 파트너 {result['partners']}명 · 귀속 {result['gross_krw']:,} KRW "
          f"· 지급예정 {result['payable_krw']:,} KRW")

    with transaction() as conn:
        rows = conn.execute(
            "SELECT p.display_name, p.tier, s.gross_krw, s.share_krw, s.override_krw, "
            "       s.holdback_krw, s.payable_krw "
            "FROM core.settlements s JOIN core.partners p ON p.id=s.partner_id "
            "WHERE s.period_end=%s ORDER BY s.share_krw DESC", (day,)).fetchall()
        print(f"\n   {'파트너':18}{'등급':10}{'귀속':>12}{'자기몫':>12}{'오버라이드':>12}{'지급예정':>12}")
        print("   " + "─" * 76)
        dist_total = Decimal("0")
        for r in rows:
            print(f"   {r['display_name'][:18]:18}{r['tier']:10}"
                  f"{Decimal(str(r['gross_krw'])):>12,.0f}{Decimal(str(r['share_krw'])):>12,.0f}"
                  f"{Decimal(str(r['override_krw'])):>12,.0f}{Decimal(str(r['payable_krw'])):>12,.0f}")
            dist_total += Decimal(str(r["share_krw"])) + Decimal(str(r["override_krw"]))
        print(f"\n   ✔ 배분 총합 {dist_total:,} == 귀속 총액 {commission:,} → "
              f"{'통과' if dist_total == commission else '실패 (차액 ' + str(dist_total - commission) + ')'}")
        return 0 if dist_total == commission else 1


if __name__ == "__main__":
    raise SystemExit(main())

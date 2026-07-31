"""네트워크 대표 오퍼 수집 — 23개 제휴 네트워크의 '모든 광고 유형' 반영.

물리 상품 외 디지털·앱설치·구독·서비스·리드·쿠폰 오퍼를 각 네트워크 프로파일대로
생성→정규화→UPSERT 하고, 점수·분류까지 돌린다. opendata 실수집분과 합쳐 다양한
오퍼 유형이 랜딩/사이트에 노출된다.

사용: python scripts/collect_networks.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("GAMDAP_DB_HOST", "127.0.0.1")
os.environ.setdefault("GAMDAP_DB_PORT", "5433")
os.environ.setdefault("GAMDAP_DB_NAME", "gamdap")
os.environ.setdefault("GAMDAP_DB_USER", "postgres")
os.environ.setdefault("GAMDAP_DB_PASSWORD", "x")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PGCLIENTENCODING", "UTF8")


def main() -> int:
    from gamdap.analytics import compute_scores
    from gamdap.analytics.classification import compute_classifications
    from gamdap.db import transaction
    from gamdap.ingest.network_offers import build_offers_for, seed_networks
    from gamdap.ingest.normalizer import normalize_offer
    from gamdap.ingest.upsert import bulk_upsert_offers
    from gamdap.members import network_catalog
    from gamdap.normalize.currency import CurrencyConverter

    print("■ 네트워크 대표 오퍼 수집 시작")

    with transaction() as conn:
        seeded = seed_networks(conn)
    print(f"  · 네트워크 시딩 신규={seeded} (총 {len(network_catalog.list_networks())})")

    total_ins = total_upd = total_built = 0
    with transaction() as conn:
        converter = CurrencyConverter.load_latest(conn)
        netmap = {r["code"]: r["id"] for r in
                  conn.execute("SELECT id, code FROM core.networks").fetchall()}

    for net in network_catalog.list_networks():
        nid = netmap.get(net["slug"])
        if nid is None:
            continue
        raws = build_offers_for(net["slug"], net["name"])
        total_built += len(raws)
        normalized = [normalize_offer(r, nid, converter, None) for r in raws]
        with transaction() as conn:
            st = bulk_upsert_offers(conn, normalized)
        total_ins += st.inserted
        total_upd += st.updated

    with transaction() as conn:
        n_score = compute_scores(conn)
    with transaction() as conn:
        n_class = compute_classifications(conn)
    # 생성 오퍼(썸네일 없음)에 실 상품 사진 백필 → 빈 이미지 방지
    from backfill_thumbnails import backfill
    with transaction() as conn:
        n_img = backfill(conn, "opendata")
    print(f"  · 썸네일 백필 {n_img}개")

    with transaction() as conn:
        by_type = conn.execute(
            "SELECT offer_type, count(*) c FROM core.offers WHERE is_active "
            "GROUP BY offer_type ORDER BY c DESC"
        ).fetchall()
        nets = conn.execute(
            "SELECT count(DISTINCT network_id) c FROM core.offers WHERE is_active"
        ).fetchone()["c"]

    print("\n■ 네트워크 대표 오퍼 수집 완료")
    print(f"  생성={total_built}  신규={total_ins}  갱신={total_upd}")
    print(f"  점수={n_score}  분류={n_class}  귀속 네트워크={nets}")
    print("  오퍼 유형별: " + ", ".join(f"{r['offer_type']}={r['c']}" for r in by_type))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

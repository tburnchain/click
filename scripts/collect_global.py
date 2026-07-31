"""글로벌 수집 파이프라인 — 한 번에 실행(수집→해소→점수→분류→기회감지).

키리스 공개 소스(opendata)에서 전체 글로벌 카탈로그를 실제 HTTP로 수집한 뒤,
엔티티 해소·수익성 점수·세그먼트 분류·변동 감지까지 end-to-end로 돌린다.
실제 제휴 커넥터(coupang/amazon/cj/impact/clickbank)는 회원이 자기 API 키를
연결하면 동일 파이프라인으로 병행 수집된다.

사용: python scripts/collect_global.py [--limit 300] [--keywords phone,laptop,...]
DB는 로컬 5433 클러스터를 기본 연결(serve_demo 와 동일 env).
"""

from __future__ import annotations

import argparse
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", default="opendata")
    ap.add_argument("--limit", type=int, default=300, help="전체 카탈로그 수집 상한")
    ap.add_argument("--keywords", default="", help="쉼표구분 키워드(옵션, 카테고리 보강용)")
    args = ap.parse_args()

    from gamdap.analytics import compute_scores
    from gamdap.analytics.classification import compute_classifications
    from gamdap.analytics.opportunities import scan_opportunities
    from gamdap.db import transaction
    from gamdap.ingest import run_ingestion
    from gamdap.ingest.entity_resolution import resolve_products

    print(f"■ 글로벌 수집 시작 — network={args.network} limit={args.limit}")

    # 1) 전체 카탈로그 수집(키워드 없이 → 페이지네이션 전체 수집)
    total_fetched = total_ins = total_upd = 0
    rep = run_ingestion(args.network, keyword=None, category=None, limit=args.limit, job_type="full")
    total_fetched += rep.fetched
    total_ins += rep.stats.inserted
    total_upd += rep.stats.updated
    print(f"  · 전체수집 status={rep.status} fetched={rep.fetched} "
          f"ins={rep.stats.inserted} upd={rep.stats.updated} err={len(rep.errors)}")

    # 2) 키워드 보강(옵션) — 검색 특화 상품 추가 확보
    for kw in [k.strip() for k in args.keywords.split(",") if k.strip()]:
        r = run_ingestion(args.network, keyword=kw, limit=100, job_type="incremental")
        total_fetched += r.fetched
        total_ins += r.stats.inserted
        total_upd += r.stats.updated
        print(f"  · '{kw}' fetched={r.fetched} ins={r.stats.inserted} upd={r.stats.updated}")

    # 3) 후처리 파이프라인
    with transaction() as conn:
        rs = resolve_products(conn)
    with transaction() as conn:
        n_score = compute_scores(conn)
    with transaction() as conn:
        n_class = compute_classifications(conn)
    with transaction() as conn:
        n_evt = scan_opportunities(conn)

    # 4) 요약
    with transaction() as conn:
        offers = conn.execute("SELECT count(*) c FROM core.offers WHERE is_active").fetchone()["c"]
        segs = conn.execute(
            "SELECT segment, count(*) c FROM analytics.product_classifications "
            "GROUP BY segment ORDER BY c DESC"
        ).fetchall()

    print("\n■ 글로벌 수집 완료")
    print(f"  수집 fetched={total_fetched}  신규={total_ins}  갱신={total_upd}")
    print(f"  엔티티해소 linked={rs.linked} created={rs.created} review={rs.review}")
    print(f"  점수={n_score}  분류={n_class}  기회이벤트={n_evt}")
    print(f"  활성 오퍼={offers}  세그먼트: " + ", ".join(f"{r['segment']}={r['c']}" for r in segs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

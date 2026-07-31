"""실제 라이브 광고상품 수집 — 키리스 실 API 원천에서 진짜 데이터 추출·DB화.

원천(모두 인증 불필요·실데이터):
  · apple_media (iTunes Search)  → 실제 앱/음악/영화/전자책 (app_install·digital_product)
  · opendata    (DummyJSON)      → 실제 물리 상품 (physical_product)

수집→정규화→UPSERT→해소→점수→분류까지 end-to-end. 생성 샘플(sample=true)과 달리
여기서 들어오는 데이터는 실 API 응답이라 is_sample=false 로 저장된다.

게이트형 네트워크(coupang/amazon/cj/impact/clickbank)는 회원이 API 키를 연결하면
동일 파이프라인으로 라이브 수집된다(커넥터·서명 구현 완료, 키 필요).

사용: python scripts/collect_real.py [--limit 300]
"""

from __future__ import annotations

import argparse
import json
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


def _ensure_network(conn, code: str, name: str, adapter: str, tracking: str, meta: dict) -> None:
    row = conn.execute("SELECT id FROM core.networks WHERE code=%s", (code,)).fetchone()
    if row:
        conn.execute("UPDATE core.networks SET display_name=%s, adapter=%s, tracking_param=%s, "
                     "is_active=true, meta=%s::jsonb, updated_at=now() WHERE code=%s",
                     (name, adapter, tracking, json.dumps(meta, ensure_ascii=False), code))
    else:
        conn.execute("INSERT INTO core.networks (code, display_name, data_source, adapter, "
                     "tracking_param, is_active, meta) VALUES (%s,%s,'official_api',%s,%s,true,%s::jsonb)",
                     (code, name, adapter, tracking, json.dumps(meta, ensure_ascii=False)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300)
    args = ap.parse_args()

    from gamdap.analytics import compute_scores
    from gamdap.analytics.classification import compute_classifications
    from gamdap.db import transaction
    from gamdap.ingest import run_ingestion
    from gamdap.ingest.entity_resolution import resolve_products

    print("■ 실 라이브 광고상품 수집 시작")

    with transaction() as conn:
        _ensure_network(conn, "apple_media", "Apple 미디어(iTunes)", "itunes", "at",
                        {"region": "🌎 글로벌", "category": "앱·디지털", "keyless": True})

    plan = [("apple_media", args.limit), ("opendata", args.limit)]
    total_fetched = total_ins = total_upd = 0
    for code, lim in plan:
        r = run_ingestion(code, keyword=None, category=None, limit=lim, job_type="full")
        total_fetched += r.fetched
        total_ins += r.stats.inserted
        total_upd += r.stats.updated
        print(f"  · {code:12} status={r.status} fetched={r.fetched} "
              f"ins={r.stats.inserted} upd={r.stats.updated} err={len(r.errors)}")
        if r.errors[:2]:
            print("      err:", r.errors[:2])

    with transaction() as conn:
        rs = resolve_products(conn)
    with transaction() as conn:
        n_score = compute_scores(conn)
    with transaction() as conn:
        n_class = compute_classifications(conn)

    with transaction() as conn:
        real = conn.execute(
            "SELECT count(*) c FROM core.offers WHERE is_active "
            "AND COALESCE((native_metric_json->>'sample')::bool, false) = false"
        ).fetchone()["c"]
        by_src = conn.execute(
            "SELECT n.code, o.offer_type, count(*) c FROM core.offers o "
            "JOIN core.networks n ON n.id=o.network_id "
            "WHERE o.is_active AND COALESCE((o.native_metric_json->>'sample')::bool,false)=false "
            "GROUP BY n.code, o.offer_type ORDER BY c DESC LIMIT 8"
        ).fetchall()

    print("\n■ 실 라이브 수집 완료")
    print(f"  fetched={total_fetched} 신규={total_ins} 갱신={total_upd}")
    print(f"  해소 linked={rs.linked} created={rs.created} · 점수={n_score} 분류={n_class}")
    print(f"  실데이터(sample 아님) 활성 오퍼={real}")
    for r in by_src:
        print(f"    {r['code']:12} {r['offer_type']:16} {r['c']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

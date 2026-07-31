"""공개 상품페이지 크롤링(Mode A) 실행 — 허가된 소스만.

기본 데모 대상은 books.toscrape.com(스크래핑 연습용 공개 샌드박스, robots 허용)이다.
실제 운영에서는 사용자가 크롤링 권한을 가진 쇼핑몰 도메인을 인자로 지정한다.

사용:
  python scripts/crawl_source.py            # 데모(books.toscrape)
  python scripts/crawl_source.py --base https://shop.example.com \\
         --list https://shop.example.com/products \\
         --pattern "/product/\\d+" --name "내 쇼핑몰" --limit 40
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
for k, v in {"GAMDAP_DB_HOST": "127.0.0.1", "GAMDAP_DB_PORT": "5433", "GAMDAP_DB_NAME": "gamdap",
             "GAMDAP_DB_USER": "postgres", "GAMDAP_DB_PASSWORD": "x",
             "PYTHONIOENCODING": "utf-8", "PGCLIENTENCODING": "UTF8"}.items():
    os.environ.setdefault(k, v)

_DEMO = {
    "base": "https://books.toscrape.com",
    "list": ["https://books.toscrape.com/catalogue/page-1.html",
             "https://books.toscrape.com/catalogue/page-2.html",
             "https://books.toscrape.com/catalogue/page-3.html"],
    "pattern": r"catalogue/[^/]+_\d+/index\.html",
    "name": "Books ToScrape (샌드박스)",
}


def _ensure_network(conn, base_url: str, name: str) -> tuple[int, str]:
    host = urlparse(base_url).netloc.lower()
    code = "crawl_" + host.replace(".", "_")[:40]
    row = conn.execute("SELECT id FROM core.networks WHERE code=%s", (code,)).fetchone()
    meta = json.dumps({"kind": "webcrawl", "host": host}, ensure_ascii=False)
    if row:
        conn.execute("UPDATE core.networks SET display_name=%s, is_active=true WHERE id=%s", (name, row["id"]))
        return row["id"], code
    nid = conn.execute(
        "INSERT INTO core.networks (code, display_name, data_source, adapter, tracking_param, "
        "is_active, meta) VALUES (%s,%s,'feed',NULL,'ref',true,%s::jsonb) RETURNING id",
        (code, name, meta)).fetchone()["id"]
    return nid, code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    ap.add_argument("--list", nargs="*")
    ap.add_argument("--pattern")
    ap.add_argument("--name")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--delay", type=float, default=0.5)
    a = ap.parse_args()
    base = a.base or _DEMO["base"]
    lists = a.list or _DEMO["list"]
    pattern = a.pattern or _DEMO["pattern"]
    name = a.name or _DEMO["name"]

    from gamdap.analytics import compute_scores
    from gamdap.analytics.classification import compute_classifications
    from gamdap.connectors.webcrawler import WebCrawler
    from gamdap.db import transaction
    from gamdap.ingest.normalizer import normalize_offer
    from gamdap.ingest.upsert import bulk_upsert_offers
    from gamdap.normalize.currency import CurrencyConverter

    print(f"■ 크롤링 시작 — {name} ({base})  robots 준수·지연 {a.delay}s")
    with transaction() as conn:
        nid, code = _ensure_network(conn, base, name)
        converter = CurrencyConverter.load_latest(conn)

    crawler = WebCrawler(delay=a.delay)
    raws = list(crawler.crawl(base_url=base, list_urls=lists, link_pattern=pattern,
                              network_code=code, limit=a.limit))
    print(f"  · 추출 {len(raws)}개 상품")
    if not raws:
        print("  robots 차단 또는 추출 실패 — 대상/패턴 확인")
        return 0
    normalized = [normalize_offer(r, nid, converter, None) for r in raws]
    with transaction() as conn:
        st = bulk_upsert_offers(conn, normalized)
    with transaction() as conn:
        compute_scores(conn)
    with transaction() as conn:
        compute_classifications(conn)
    print(f"■ 완료: 신규 {st.inserted} · 갱신 {st.updated} → '지금 수집된 광고상품'에 리스팅")
    print("  샘플:", ", ".join(r.title[:30] for r in raws[:3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""썸네일 백필 — 이미지 없는 오퍼에 실제 상품 사진을 채운다.

모든 빌더 사이트에서 회색 빈 이미지가 노출되지 않도록, thumbnail_url 이 없는 오퍼에
이미지 보유 오퍼(기본: opendata 실 상품 사진 — 프레스티지몰 등이 쓰는 사진 풀)에서
결정적으로(offer id 기준) 이미지를 빌려 채운다.

사용: python scripts/backfill_thumbnails.py [--source opendata]
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


def backfill(conn, source: str = "opendata") -> int:
    """이미지 풀에서 빌려 null 썸네일을 채운다. 채운 개수 반환."""
    pool = [r["thumbnail_url"] for r in conn.execute(
        "SELECT DISTINCT o.thumbnail_url FROM core.offers o JOIN core.networks n ON n.id=o.network_id "
        "WHERE n.code=%s AND o.thumbnail_url IS NOT NULL AND o.thumbnail_url<>'' ORDER BY 1",
        (source,),
    ).fetchall()]
    if not pool:
        # 원천 없으면 전체 이미지 풀에서
        pool = [r["thumbnail_url"] for r in conn.execute(
            "SELECT DISTINCT thumbnail_url FROM core.offers "
            "WHERE thumbnail_url IS NOT NULL AND thumbnail_url<>'' ORDER BY 1"
        ).fetchall()]
    if not pool:
        return 0
    targets = conn.execute(
        "SELECT id FROM core.offers WHERE is_active AND (thumbnail_url IS NULL OR thumbnail_url='') ORDER BY id"
    ).fetchall()
    n = 0
    for row in targets:
        img = pool[row["id"] % len(pool)]
        conn.execute("UPDATE core.offers SET thumbnail_url=%s WHERE id=%s", (img, row["id"]))
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="opendata", help="이미지 원천 네트워크 코드")
    args = ap.parse_args()
    from gamdap.db import transaction

    with transaction() as conn:
        n = backfill(conn, args.source)
        pool = conn.execute(
            "SELECT count(DISTINCT thumbnail_url) c FROM core.offers o JOIN core.networks n ON n.id=o.network_id "
            "WHERE n.code=%s AND o.thumbnail_url IS NOT NULL", (args.source,)).fetchone()["c"]
        left = conn.execute(
            "SELECT count(*) c FROM core.offers WHERE is_active AND (thumbnail_url IS NULL OR thumbnail_url='')"
        ).fetchone()["c"]
    print(f"■ 썸네일 백필 완료: {n}개 채움 (원천 {args.source} 이미지 {pool}종) · 남은 빈 이미지 {left}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

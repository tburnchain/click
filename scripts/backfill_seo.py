"""기존 사이트에 독창적 SEO 소급 적용 — 중복 콘텐츠 회피.

이 기능 도입 이전에 생성된 사이트(config에 seo_auto 없음)에 각 slug 시드로
독창적 SEO 카피를 생성해 병합한다(사용자가 이미 수정한 값은 보존).

사용: python scripts/backfill_seo.py [--force]
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="이미 seo_auto 있어도 재생성")
    args = ap.parse_args()
    from gamdap.db import transaction
    from gamdap.members import seo_unique

    with transaction() as conn:
        rows = conn.execute(
            "SELECT s.id, s.slug, s.title, s.config, t.kind FROM core.member_sites s "
            "JOIN core.builder_templates t ON t.id=s.template_id"
        ).fetchall()
        n = 0
        for r in rows:
            cfg = r["config"] or {}
            if cfg.get("seo_auto") and not args.force:
                continue
            gen = seo_unique.generate_profile(r["slug"], r["title"], r["kind"])
            # --force: 자동 SEO 키를 갱신(색상·추적 등 나머지 설정은 유지)
            merged = {**cfg, **gen} if args.force else seo_unique.merge_into_config(cfg, gen)
            conn.execute("UPDATE core.member_sites SET config=%s WHERE id=%s",
                         (json.dumps(merged, ensure_ascii=False), r["id"]))
            n += 1
    print(f"■ 독창적 SEO 소급 적용: {n}/{len(rows)} 사이트")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

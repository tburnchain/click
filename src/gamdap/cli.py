"""GAMDAP CLI.

사용:
    python -m gamdap.cli migrate
    python -m gamdap.cli ingest --network coupang_partners --keyword 에어프라이어 --limit 30
    python -m gamdap.cli health --network coupang_partners
"""

from __future__ import annotations

import argparse
import sys

from gamdap.logging import get_logger

log = get_logger("cli")


def migrate(_args: argparse.Namespace | None = None) -> int:
    from gamdap.db.migrate import run_migrations

    applied = run_migrations()
    print(f"✓ 마이그레이션 완료 (신규 적용 {applied}건)")
    return 0


def ingest(args: argparse.Namespace) -> int:
    from gamdap.ingest import run_ingestion

    report = run_ingestion(
        args.network, keyword=args.keyword, category=args.category,
        limit=args.limit, job_type=args.job_type,
    )
    print(
        f"[{report.network_code}] status={report.status} fetched={report.fetched} "
        f"inserted={report.stats.inserted} updated={report.stats.updated} "
        f"unchanged={report.stats.unchanged} errors={len(report.errors)}"
    )
    return 0 if report.status in ("success", "partial") else 1


def fx_sync(args: argparse.Namespace) -> int:
    from gamdap.db import transaction
    from gamdap.normalize.fx_source import sync_exchange_rates

    with transaction() as conn:
        n = sync_exchange_rates(conn, provider=args.provider)
    print(f"✓ 환율 동기화 완료 (provider={args.provider}, {n} pairs)")
    return 0


def score(_args: argparse.Namespace) -> int:
    from gamdap.analytics import compute_scores
    from gamdap.db import transaction

    with transaction() as conn:
        n = compute_scores(conn)
    print(f"✓ 수익성 점수 계산 완료 ({n} offers)")
    return 0


def ensure_partitions(_args: argparse.Namespace) -> int:
    from gamdap.db import transaction
    from gamdap.db.partitions import drop_old_partitions, ensure_month_partitions

    with transaction() as conn:
        created = ensure_month_partitions(conn, months_ahead=2)
        dropped = drop_old_partitions(conn, retain_months=12)
    print(f"✓ 파티션 준비 {len(created)}개 · 보존초과 정리 {len(dropped)}개")
    return 0


def resolve(_args: argparse.Namespace) -> int:
    from gamdap.db import transaction
    from gamdap.ingest.entity_resolution import resolve_products

    with transaction() as conn:
        s = resolve_products(conn)
    print(f"✓ 엔티티 해소 완료 (linked={s.linked} created={s.created} review={s.review})")
    return 0


def classify(_args: argparse.Namespace) -> int:
    from gamdap.analytics.classification import compute_classifications
    from gamdap.db import transaction

    with transaction() as conn:
        n = compute_classifications(conn)
    print(f"✓ 광고상품 분류 완료 ({n} offers)")
    return 0


def scan_opportunities(_args: argparse.Namespace) -> int:
    from gamdap.analytics.opportunities import scan_opportunities as scan
    from gamdap.db import transaction

    with transaction() as conn:
        n = scan(conn)
    print(f"✓ 기회 이벤트 감지 완료 ({n} events)")
    return 0


def health(args: argparse.Namespace) -> int:
    from gamdap.connectors import get_connector

    adapter = {"coupang_partners": "coupang"}.get(args.network, args.network)
    ok = get_connector(adapter).health()
    print(f"{args.network}: {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gamdap")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate", help="DB 마이그레이션 적용").set_defaults(func=migrate)

    pi = sub.add_parser("ingest", help="네트워크 수집 실행")
    pi.add_argument("--network", required=True)
    pi.add_argument("--keyword", default=None)
    pi.add_argument("--category", default=None)
    pi.add_argument("--limit", type=int, default=50)
    pi.add_argument("--job-type", dest="job_type", default="incremental")
    pi.set_defaults(func=ingest)

    pf = sub.add_parser("fx-sync", help="환율 동기화")
    pf.add_argument("--provider", default="ecb", choices=["ecb", "manual"])
    pf.set_defaults(func=fx_sync)

    sub.add_parser("score", help="수익성 점수 계산").set_defaults(func=score)
    sub.add_parser("ensure-partitions", help="월 파티션 자동생성/보존정리").set_defaults(func=ensure_partitions)
    sub.add_parser("resolve", help="엔티티 해소(상품-오퍼 연결)").set_defaults(func=resolve)
    sub.add_parser("classify", help="광고상품 분류(세그먼트)").set_defaults(func=classify)
    sub.add_parser("scan-opportunities", help="변동 감지(기회 이벤트)").set_defaults(func=scan_opportunities)

    ph = sub.add_parser("health", help="커넥터 상태 확인")
    ph.add_argument("--network", required=True)
    ph.set_defaults(func=health)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

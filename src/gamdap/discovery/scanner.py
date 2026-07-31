"""자가확장 발견 스캐너(§16) — 소스 스캔 → 후보 평가 → 검증 → 온보딩 + UCB 탐사.

발견은 '후보 생성'까지만. 공식/애그리게이터 API·승인 피드를 갖춰야 커넥터로 승격(§16 원칙).
실제 웹 스캔(prober)은 주입식 → 테스트 시 결정론적 프로브로 대체.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gamdap.discovery.scoring import (
    Arm,
    CandidateSignals,
    candidate_score,
    select_arm,
    update_arm,
)
from gamdap.logging import get_logger

if TYPE_CHECKING:
    from psycopg import Connection

log = get_logger("discovery.scanner")


@dataclass
class CandidateProbe:
    """소스에서 발견한 네트워크 후보 + 검증 시그널."""

    name: str
    home_url: str | None = None
    program_url: str | None = None
    country_iso: str | None = None
    has_official_api: bool = False
    api_doc_url: str | None = None
    has_product_feed: bool = False
    feed_url: str | None = None
    terms_scrape_allowed: bool = False
    est_commission_hint: str | None = None
    category_fit: float = 0.5
    commission_viability: float = 0.5
    country_priority: float = 0.5


def evaluate_candidate(probe: CandidateProbe, source_trust: float) -> float:
    """후보 스코어(§16.4). 순수 함수 — 곱셈 게이트 포함."""
    return candidate_score(CandidateSignals(
        source_trust=source_trust,
        has_official_api=probe.has_official_api,
        has_product_feed=probe.has_product_feed,
        terms_scrape_allowed=probe.terms_scrape_allowed,
        category_fit=probe.category_fit,
        commission_viability=probe.commission_viability,
        country_priority=probe.country_priority,
    ))


# 소스 → 후보 목록 프로브 규격(주입식)
Prober = Callable[[dict], list[CandidateProbe]]


def scan_sources(conn: Connection, prober: Prober, *, min_score: float = 1.0) -> int:
    """활성 소스를 스캔해 후보를 평가·적재. 신규 후보 수 반환."""
    sources = conn.execute(
        "SELECT id, code, trust, meta FROM core.discovery_sources WHERE is_enabled ORDER BY trust DESC"
    ).fetchall()
    inserted = 0
    for src in sources:
        trust = float(src["trust"])
        for probe in prober(dict(src)):
            score = evaluate_candidate(probe, trust)
            if score < min_score:
                continue  # 게이트 탈락(원천/약관 결격 등) → 후보 등록 안 함
            # 이미 등록된 네트워크면 중복 표시
            dup = conn.execute(
                "SELECT id FROM core.networks WHERE lower(display_name) = lower(%s)",
                (probe.name,),
            ).fetchone()
            n = conn.execute(
                """
                INSERT INTO core.network_candidates
                    (name, home_url, program_url, country_iso, discovered_by,
                     has_official_api, api_doc_url, has_product_feed, feed_url,
                     terms_scrape_allowed, est_commission_hint, category_fit,
                     commission_viability, country_priority, duplicate_of, candidate_score, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        CASE WHEN %s::bigint IS NOT NULL THEN 'rejected' ELSE 'pending' END)
                ON CONFLICT DO NOTHING
                """,
                (probe.name, probe.home_url, probe.program_url, probe.country_iso, src["id"],
                 probe.has_official_api, probe.api_doc_url, probe.has_product_feed, probe.feed_url,
                 probe.terms_scrape_allowed, probe.est_commission_hint, probe.category_fit,
                 probe.commission_viability, probe.country_priority,
                 dup["id"] if dup else None, round(score, 3),
                 dup["id"] if dup else None),
            ).rowcount
            inserted += n
        conn.execute("UPDATE core.discovery_sources SET last_scanned_at=now() WHERE id=%s", (src["id"],))
    log.info("discovery.scan_done", candidates=inserted)
    return inserted


def onboard_candidate(conn: Connection, candidate_id: int, *,
                      adapter: str | None = None, reviewer: int | None = None) -> int | None:
    """후보 승인 → 네트워크로 편입. 커넥터(adapter) 있으면 active. network_id 반환."""
    c = conn.execute(
        "SELECT * FROM core.network_candidates WHERE id=%s AND status IN ('pending','approved','vetting')",
        (candidate_id,),
    ).fetchone()
    if c is None:
        return None

    data_source = "aggregator_api" if c["has_official_api"] else "feed"
    country_id = None
    if c["country_iso"]:
        row = conn.execute("SELECT id FROM core.countries WHERE iso_code=%s",
                           (c["country_iso"],)).fetchone()
        country_id = row["id"] if row else None

    code = c["name"].lower().replace(" ", "_")[:60]
    net = conn.execute(
        "INSERT INTO core.networks (code, display_name, home_country_id, data_source, adapter, "
        "api_base_url, is_active) VALUES (%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (code) DO UPDATE SET adapter=EXCLUDED.adapter RETURNING id",
        (code, c["name"], country_id, data_source, adapter,
         c["api_doc_url"] or c["home_url"], adapter is not None),
    ).fetchone()
    conn.execute(
        "UPDATE core.network_candidates SET status='onboarded', reviewed_by=%s, reviewed_at=now() "
        "WHERE id=%s", (reviewer, candidate_id),
    )
    return int(net["id"])


def reject_candidate(conn: Connection, candidate_id: int, reviewer: int | None = None) -> bool:
    n = conn.execute(
        "UPDATE core.network_candidates SET status='rejected', reviewed_by=%s, reviewed_at=now() "
        "WHERE id=%s AND status != 'onboarded'", (reviewer, candidate_id),
    ).rowcount
    return n > 0


# ── UCB 탐사 정책(§16.3) ──────────────────────────────

def next_arm(conn: Connection, c: float = 1.0) -> str | None:
    """UCB 최댓값 arm(크롤 대상 네트워크×카테고리) 선택."""
    rows = conn.execute(
        "SELECT arm_key, reward_mean, pulls FROM core.discovery_arms"
    ).fetchall()
    arms = [Arm(key=r["arm_key"], reward_mean=float(r["reward_mean"]), pulls=r["pulls"]) for r in rows]
    chosen = select_arm(arms, c)
    return chosen.key if chosen else None


def record_arm_reward(conn: Connection, arm_key: str, reward: float,
                      network_code: str | None = None, category_slug: str | None = None) -> None:
    """arm 보상(발견 수익가치/크롤비용) 기록 + 온라인 평균 갱신."""
    row = conn.execute(
        "SELECT reward_sum, pulls FROM core.discovery_arms WHERE arm_key=%s", (arm_key,)
    ).fetchone()
    prev_sum = float(row["reward_sum"]) if row else 0.0
    prev_pulls = int(row["pulls"]) if row else 0
    new_sum, new_pulls, new_mean = update_arm(prev_sum, prev_pulls, reward)
    conn.execute(
        "INSERT INTO core.discovery_arms "
        "(arm_key, network_code, category_slug, pulls, reward_sum, reward_mean, last_pulled_at) "
        "VALUES (%s,%s,%s,%s,%s,%s, now()) "
        "ON CONFLICT (arm_key) DO UPDATE SET pulls=EXCLUDED.pulls, reward_sum=EXCLUDED.reward_sum, "
        "reward_mean=EXCLUDED.reward_mean, last_pulled_at=now()",
        (arm_key, network_code, category_slug, new_pulls, new_sum, new_mean),
    )

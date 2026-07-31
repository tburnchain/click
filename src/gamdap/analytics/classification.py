"""광고상품 분류 엔진(§18) — 초지능 수학.

파이프라인:
  1) 특징 벡터: 의미 임베딩(textvec) — AI 'embedding' 역량이 켜지면 라우팅, 아니면 해싱 폴백
  2) 계층 분류: 카테고리 중심점 코사인 + 소프트맥스 신뢰도
  3) 니치 발견: 코사인 임계 그리디 군집(HDBSCAN 대체, 이식성)
  4) 경쟁 수학: 공급밀도 · HHI · 엔트로피 → 경쟁지수 K
  5) 기회 사분면: O = Π^a·D^b·(1−K)^c → 금맥/신흥/안정/포화/회피

순수 함수(테스트 가능) + compute_classifications(conn) 잡으로 분리.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gamdap.analytics.profitability import price_tier, robust_quantile_norm
from gamdap.textvec import cosine, hashing_embedding, softmax

if TYPE_CHECKING:
    from psycopg import Connection


# ── 경쟁·포화 수학(§18.5) ──────────────────────────────

def hhi(shares: list[float]) -> float:
    """허핀달-허시먼 지수(0~1). 소수 독점일수록 1에 근접."""
    total = sum(shares)
    if total <= 0:
        return 0.0
    return sum((s / total) ** 2 for s in shares)


def entropy_norm(shares: list[float]) -> float:
    """정규화 섀넌 엔트로피(0~1). 파편화될수록 1."""
    total = sum(shares)
    if total <= 0 or len(shares) <= 1:
        return 0.0
    ps = [s / total for s in shares if s > 0]
    h = -sum(p * math.log(p) for p in ps)
    return h / math.log(len(shares))


def competition_index(supply_norm: float, hhi_val: float, entropy_val: float,
                      wa: float = 0.5, wb: float = 0.35, wc: float = 0.25) -> float:
    """K = clamp(wa·공급밀도 + wb·HHI − wc·엔트로피). 높을수록 붐빔."""
    k = wa * supply_norm + wb * hhi_val - wc * entropy_val
    return max(0.0, min(1.0, k))


# ── 기회 사분면(§18.6) ────────────────────────────────

def opportunity_score(pi: float, demand: float, competition: float,
                      a: float = 0.4, b: float = 0.35, c: float = 0.25) -> float:
    """O = Π^a · D^b · (1−K)^c (곱셈적, 0~1)."""
    return (max(pi, 0.0) ** a) * (max(demand, 0.0) ** b) * (max(1.0 - competition, 0.0) ** c)


@dataclass
class SegmentThresholds:
    pi_hi: float
    pi_lo: float
    d_hi: float
    d_lo: float
    k_hi: float
    k_lo: float


def assign_segment(pi: float, demand: float, competition: float, th: SegmentThresholds) -> str:
    """카테고리 상대 분위수 기준으로 세그먼트 배정(§18.6)."""
    if pi < th.pi_lo or demand < th.d_lo:
        return "avoid"
    if pi >= th.pi_hi and demand >= th.d_hi and competition <= th.k_lo:
        return "goldmine"
    if pi >= th.pi_hi and demand >= th.d_hi:
        return "cashcow"                       # 검증됐지만 경쟁 높음
    if competition <= th.k_lo and pi >= th.pi_lo:
        return "rising"                        # 저경쟁 신흥
    if competition >= th.k_hi:
        return "saturated"
    return "rising" if competition < th.k_hi else "saturated"


def classify_intent(title: str, category_slug: str | None, price_krw: float | None) -> str:
    """구매 의도 휴리스틱."""
    t = (title or "").lower()
    if any(w in t for w in ("해결", "효과", "개선", "치료", "완화", "cure", "relief", "fix")):
        return "problem_solving"
    if any(w in t for w in ("선물", "gift", "기프트")):
        return "gift"
    if category_slug and category_slug.startswith("digital"):
        return "considered"
    if price_krw is not None and price_krw < 20_000:
        return "impulse"
    return "considered"


# ── 니치 군집(§18.4) — HDBSCAN 대체(코사인 임계 그리디) ──

def cluster_embeddings(items: list[tuple[int, list[float]]], threshold: float = 0.6
                       ) -> list[list[int]]:
    """(id, embedding) 목록을 코사인 유사도 임계로 그리디 군집. 결정론적.

    반환: 군집별 id 리스트. 첫 원소를 시드로 threshold 이상이면 흡수.
    """
    clusters: list[tuple[list[float], list[int]]] = []
    for item_id, emb in items:
        best_i, best_sim = -1, threshold
        for i, (centroid, _members) in enumerate(clusters):
            sim = cosine(emb, centroid)
            if sim >= best_sim:
                best_i, best_sim = i, sim
        if best_i >= 0:
            clusters[best_i][1].append(item_id)
        else:
            clusters.append((emb, [item_id]))
    return [members for _c, members in clusters]


# ── 계층 분류(§18.3) ──────────────────────────────────

def classify_category(emb: list[float], centroids: dict[int, list[float]],
                      temperature: float = 0.2) -> tuple[int | None, float]:
    """카테고리 중심점과 코사인 → 소프트맥스 최대확률. (category_id, confidence)."""
    if not centroids:
        return None, 0.0
    ids = list(centroids)
    sims = [cosine(emb, centroids[cid]) for cid in ids]
    probs = softmax(sims, temperature)
    best = max(range(len(ids)), key=lambda i: probs[i])
    return ids[best], round(probs[best], 3)


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


# ── 계산 잡(DB) ────────────────────────────────────────

def compute_classifications(conn: Connection, embedding_dim: int = 64) -> int:
    """활성 오퍼를 분류·세그먼트화해 analytics.product_classifications 에 UPSERT. 처리 수 반환."""
    rows = conn.execute(
        """
        SELECT o.id, o.title, o.price_krw, o.network_id,
               COALESCE(c.slug, 'uncategorized') AS category_slug,
               ps.expected_epc, ps.demand_index
        FROM core.offers o
        LEFT JOIN core.products p ON p.id = o.product_id
        LEFT JOIN core.categories c ON c.id = p.category_id
        LEFT JOIN analytics.profitability_scores ps ON ps.offer_id = o.id
        WHERE o.is_active
        """
    ).fetchall()
    if not rows:
        return 0

    # 카테고리 그룹 통계(경쟁 수학 + 분위수 임계)
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["category_slug"], []).append(r)

    max_cat_size = max(len(v) for v in by_cat.values())
    cat_competition: dict[str, float] = {}
    cat_thresholds: dict[str, SegmentThresholds] = {}
    for slug, items in by_cat.items():
        # 공급밀도
        supply = len(items) / max_cat_size if max_cat_size else 0.0
        # 네트워크 점유 분포 → HHI/엔트로피
        net_counts: dict[int, int] = {}
        for it in items:
            net_counts[it["network_id"]] = net_counts.get(it["network_id"], 0) + 1
        shares = list(net_counts.values())
        k = competition_index(supply, hhi([float(s) for s in shares]),
                              entropy_norm([float(s) for s in shares]))
        cat_competition[slug] = k

        epcs = sorted(float(it["expected_epc"] or 0) for it in items)
        demands = sorted(float(it["demand_index"] or 0) for it in items)
        cat_thresholds[slug] = SegmentThresholds(
            pi_hi=robust_quantile_norm(_quantile(epcs, 0.75), epcs),
            pi_lo=robust_quantile_norm(_quantile(epcs, 0.25), epcs),
            d_hi=_quantile(demands, 0.75), d_lo=_quantile(demands, 0.25),
            k_hi=0.66, k_lo=0.33,
        )

    n = 0
    for r in rows:
        slug = r["category_slug"]
        items = by_cat[slug]
        epcs = [float(it["expected_epc"] or 0) for it in items]
        pi = robust_quantile_norm(float(r["expected_epc"] or 0), epcs)
        demand = float(r["demand_index"] or 0.5)
        k = cat_competition[slug]
        o_score = opportunity_score(pi, demand, k)
        segment = assign_segment(pi, demand, k, cat_thresholds[slug])
        intent = classify_intent(r["title"], None if slug == "uncategorized" else slug,
                                 float(r["price_krw"]) if r["price_krw"] is not None else None)
        emb = hashing_embedding(r["title"], embedding_dim)

        conn.execute(
            """
            INSERT INTO analytics.product_classifications
                (offer_id, intent, price_tier, competition_index, opportunity_score,
                 segment, embedding, method, classified_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (offer_id) DO UPDATE SET
                intent=EXCLUDED.intent, price_tier=EXCLUDED.price_tier,
                competition_index=EXCLUDED.competition_index,
                opportunity_score=EXCLUDED.opportunity_score, segment=EXCLUDED.segment,
                embedding=EXCLUDED.embedding, method=EXCLUDED.method, classified_at=now()
            """,
            (r["id"], intent, price_tier(float(r["price_krw"]) if r["price_krw"] is not None else None),
             round(k, 3), round(o_score, 3), segment, emb, "hashing_fallback"),
        )
        n += 1
    return n

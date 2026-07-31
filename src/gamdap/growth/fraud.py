"""부정 트래픽 탐지 — 위탁 확장에서 지급 전에 걸러야 할 신호들.

위탁 모델의 구조적 취약점: 파트너는 클릭·전환을 늘릴수록 보상을 받으므로,
봇 클릭·자기 클릭·유입 세탁의 유인이 존재한다. 지급 후 회수는 사실상 불가하므로
정산 **전** 단계에서 통계적으로 이상을 잡아야 한다.

적용 수학
  · 시간 엔트로피: 사람의 클릭은 시간대별로 불균등(일주기). 봇은 균일하거나
    한 시각에 집중된다. Shannon 엔트로피를 이론최대(log2 24)로 정규화해
    '너무 균일' 과 '너무 집중' 양쪽을 모두 이상으로 본다.
  · 포아송 상한: 평소 시간당 클릭률 λ 대비 관측 k 가 얼마나 비정상인가.
    P(X≥k) 를 상측 꼬리확률로 계산해 버스트를 탐지한다.
  · 허핀달 지수(HHI): IP/UA 집중도. 소수 출처가 트래픽을 지배하면 자기클릭 의심.
  · 전환율 이상치: 로버스트 z점수(중앙값·MAD 기반)로 모집단 대비 이탈 측정.
    평균·표준편차는 이상치 자체에 오염되므로 사용하지 않는다.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "Signal", "time_entropy", "poisson_upper_tail", "herfindahl",
    "robust_zscore", "detect_click_burst", "detect_low_entropy",
    "detect_concentration", "detect_cvr_outlier", "evaluate_partner",
]


@dataclass(frozen=True)
class Signal:
    kind: str
    severity: str        # 'info'|'warn'|'critical'
    score: float         # 0~1 (위험도)
    evidence: dict


def time_entropy(hours: Sequence[int]) -> float:
    """시간대(0~23) 분포의 정규화 Shannon 엔트로피 0~1.

    1.0 = 완전 균일(24시간 고르게 — 봇 의심), 0.0 = 한 시각 집중(스크립트 의심).
    사람의 자연 트래픽은 대략 0.75~0.92 구간에 든다.
    """
    if not hours:
        return 0.0
    counts = Counter(h % 24 for h in hours)
    n = sum(counts.values())
    ent = -sum((c / n) * math.log2(c / n) for c in counts.values() if c > 0)
    return ent / math.log2(24)


def poisson_upper_tail(k: int, lam: float) -> float:
    """P(X ≥ k), X~Poisson(λ). 클릭 버스트의 통계적 희귀도.

    값이 매우 작으면(예: 1e-6) 우연으로 보기 어려운 급증이다.
    """
    if lam <= 0:
        return 0.0 if k > 0 else 1.0
    if k <= 0:
        return 1.0
    # P(X≥k) = 1 - Σ_{i<k} e^-λ λ^i / i!  — 언더플로 방지를 위해 누적을 로그 없이 순차 계산
    term = math.exp(-lam)
    cum = term
    for i in range(1, k):
        term *= lam / i
        cum += term
        if cum >= 1.0:
            return 0.0
    return max(0.0, 1.0 - cum)


def herfindahl(values: Sequence[str]) -> float:
    """허핀달-허시먼 집중도 0~1. 1 = 단일 출처가 전부."""
    if not values:
        return 0.0
    counts = Counter(values)
    n = len(values)
    return sum((c / n) ** 2 for c in counts.values())


def robust_zscore(value: float, population: Sequence[float]) -> float:
    """중앙값·MAD 기반 로버스트 z점수. 이상치에 오염되지 않는다.

    z = 0.6745 × (x - median) / MAD   (0.6745 는 정규분포에서 MAD→σ 환산계수)
    """
    if len(population) < 3:
        return 0.0
    vals = sorted(population)
    mid = len(vals) // 2
    median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
    devs = sorted(abs(v - median) for v in vals)
    mad = devs[mid] if len(devs) % 2 else (devs[mid - 1] + devs[mid]) / 2
    if mad <= 1e-12:
        return 0.0
    return 0.6745 * (value - median) / mad


# ── 개별 탐지기 ───────────────────────────────────────────────
def detect_click_burst(recent_clicks: int, baseline_hourly: float) -> Signal | None:
    """평소 대비 시간당 클릭 급증."""
    p = poisson_upper_tail(recent_clicks, max(baseline_hourly, 0.1))
    if p >= 1e-3:
        return None
    severity = "critical" if p < 1e-9 else "warn"
    return Signal("click_burst", severity, min(1.0, -math.log10(max(p, 1e-300)) / 12.0),
                  {"clicks": recent_clicks, "baseline_hourly": round(baseline_hourly, 3),
                   "p_value": p})


def detect_low_entropy(hours: Sequence[int], *, min_samples: int = 30) -> Signal | None:
    """시간분포가 부자연스러움(너무 균일 또는 너무 집중)."""
    if len(hours) < min_samples:
        return None
    e = time_entropy(hours)
    if e > 0.97:
        return Signal("low_entropy", "warn", min(1.0, (e - 0.97) / 0.03),
                      {"entropy": round(e, 4), "reason": "균일 분포(봇 스케줄러 의심)"})
    if e < 0.25:
        return Signal("low_entropy", "warn", min(1.0, (0.25 - e) / 0.25),
                      {"entropy": round(e, 4), "reason": "단일 시각 집중(스크립트 의심)"})
    return None


def detect_concentration(ip_hashes: Sequence[str], *, threshold: float = 0.35) -> Signal | None:
    """소수 IP 가 트래픽을 지배(자기클릭·프록시 팜 의심)."""
    if len(ip_hashes) < 20:
        return None
    hhi = herfindahl(ip_hashes)
    if hhi < threshold:
        return None
    severity = "critical" if hhi >= 0.6 else "warn"
    return Signal("ip_concentration", severity, min(1.0, hhi),
                  {"hhi": round(hhi, 4), "unique_ips": len(set(ip_hashes)),
                   "total": len(ip_hashes)})


def detect_cvr_outlier(cvr: float, population_cvr: Sequence[float],
                       clicks: int, *, min_clicks: int = 50) -> Signal | None:
    """전환율이 모집단에서 비정상적으로 이탈(과대 = 위조 전환 의심)."""
    if clicks < min_clicks or len(population_cvr) < 5:
        return None
    z = robust_zscore(cvr, population_cvr)
    if z < 4.0:
        return None
    return Signal("cvr_outlier", "critical" if z >= 8 else "warn",
                  min(1.0, z / 12.0), {"cvr": round(cvr, 6), "robust_z": round(z, 2)})


def detect_bot_ratio(bot_clicks: int, total_clicks: int,
                     *, threshold: float = 0.15) -> Signal | None:
    """봇 판정 클릭 비중 과다."""
    if total_clicks < 20:
        return None
    ratio = bot_clicks / total_clicks
    if ratio < threshold:
        return None
    return Signal("bot_ratio", "critical" if ratio >= 0.4 else "warn", min(1.0, ratio),
                  {"bot_ratio": round(ratio, 4), "bot_clicks": bot_clicks,
                   "total": total_clicks})


def evaluate_partner(*, hours: Sequence[int], ip_hashes: Sequence[str],
                     recent_clicks: int, baseline_hourly: float,
                     cvr: float, population_cvr: Sequence[float],
                     clicks: int, bot_clicks: int) -> list[Signal]:
    """파트너 1인에 대한 전체 탐지 실행. 신호 리스트(없으면 빈 리스트)."""
    found = [
        detect_click_burst(recent_clicks, baseline_hourly),
        detect_low_entropy(hours),
        detect_concentration(ip_hashes),
        detect_cvr_outlier(cvr, population_cvr, clicks),
        detect_bot_ratio(bot_clicks, clicks),
    ]
    return [s for s in found if s is not None]


def risk_score(signals: Sequence[Signal]) -> float:
    """신호들을 0~100 위험도로 통합.

    독립 사건의 여집합 곱(noisy-OR): 여러 약한 신호가 모이면 위험이 누적되지만
    100 을 넘지 않는다. severity 로 가중.
    """
    weight = {"info": 0.3, "warn": 0.7, "critical": 1.0}
    survive = 1.0
    for s in signals:
        survive *= (1.0 - min(0.99, s.score * weight.get(s.severity, 0.5)))
    return round(100.0 * (1.0 - survive), 2)

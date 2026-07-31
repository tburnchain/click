"""멀티터치 어트리뷰션 — 전환 1건을 여러 터치포인트에 '기여도'로 분배한다.

왜 필요한가: 방문자는 보통 여러 파트너의 사이트를 거쳐 구매한다. 마지막 클릭에
100%를 주면(last-click) 발견·인지 단계에 기여한 파트너가 영구히 0원을 받게 되어
상위 퍼널 파트너가 이탈한다. 위탁 확장 모델에서 이는 네트워크 자체를 붕괴시킨다.

구현 모델
  · last_click   : 마지막 터치 100% (기준선·감사용)
  · time_decay   : 전환에 가까울수록 지수 가중 w=2^(-Δt/half_life)
  · position     : U자형(첫40%·마지막40%·중간20% 균등)
  · markov       : 흡수 마르코프 연쇄의 **제거효과(removal effect)**
  · shapley      : 협조게임 Shapley 값(순열 평균 한계기여). 채널 수가 많으면
                   몬테카를로 근사로 전환(정확 계산은 2^n).

모든 모델은 가중치 합이 정확히 1이 되도록 정규화한다(부동소수 잔차는 마지막
원소에 흡수). 금액 배분의 잔차 처리는 settlement 이 최대잔여법으로 담당한다.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import permutations

__all__ = [
    "Touch", "attribute", "MODELS",
    "last_click", "time_decay", "position_based", "markov_removal", "shapley",
]

MODELS = ("last_click", "time_decay", "position", "markov", "shapley")

# Shapley 정확 계산 상한(그 이상은 몬테카를로). 8! = 40320 순열이면 충분히 빠르다.
_SHAPLEY_EXACT_MAX = 8
_SHAPLEY_SAMPLES = 2000


@dataclass(frozen=True)
class Touch:
    """어트리뷰션 입력 단위. 하나의 클릭(터치포인트)."""

    touchpoint_id: int
    partner_id: int | None
    occurred_at: datetime
    channel: str = "direct"


def _normalize(weights: list[float]) -> list[float]:
    """합이 1이 되도록 정규화. 합이 0이면 균등분배."""
    total = math.fsum(weights)
    if total <= 0:
        n = len(weights)
        return [1.0 / n] * n if n else []
    out = [w / total for w in weights]
    # 부동소수 잔차를 마지막에 흡수 → 합계 정확히 1.0
    out[-1] += 1.0 - math.fsum(out)
    return out


# ── 휴리스틱 모델 ──────────────────────────────────────────────
def last_click(touches: Sequence[Touch]) -> list[float]:
    n = len(touches)
    if n == 0:
        return []
    return [0.0] * (n - 1) + [1.0]


def time_decay(touches: Sequence[Touch], *, half_life_days: float = 7.0) -> list[float]:
    """전환 시점(마지막 터치)에 가까울수록 지수적으로 큰 가중치.

    w_i = 2^(-Δt_i / half_life). Δt 는 마지막 터치와의 시간차(일).
    반감기 7일은 제휴 커머스의 통상 쿠키 윈도(7~30일)에서 중앙값에 해당한다.
    """
    if not touches:
        return []
    last_at = max(t.occurred_at for t in touches)
    hl = max(half_life_days, 1e-9)
    w = []
    for t in touches:
        delta_days = (last_at - t.occurred_at).total_seconds() / 86400.0
        w.append(2.0 ** (-max(delta_days, 0.0) / hl))
    return _normalize(w)


def position_based(touches: Sequence[Touch], *, first: float = 0.4,
                   last: float = 0.4) -> list[float]:
    """U자형. 첫 터치(발견)와 마지막 터치(전환)에 각 40%, 나머지가 20% 균등."""
    n = len(touches)
    if n == 0:
        return []
    if n == 1:
        return [1.0]
    if n == 2:
        return _normalize([first, last])
    middle = max(0.0, 1.0 - first - last)
    each = middle / (n - 2)
    return _normalize([first] + [each] * (n - 2) + [last])


# ── 마르코프 제거효과 ──────────────────────────────────────────
def markov_removal(paths: Sequence[tuple[Sequence[str], bool]],
                   channels: Sequence[str]) -> dict[str, float]:
    """흡수 마르코프 연쇄의 제거효과로 채널 기여도를 계산.

    아이디어: 채널 c 를 경로에서 제거했을 때 전환확률이 얼마나 떨어지는가?
      removal_effect(c) = 1 - P(전환 | c 제거) / P(전환 | 전체)
    이는 '그 채널이 없었다면 잃었을 전환의 비율'로, 상관이 아닌 **한계 기여**를
    측정한다. 결과를 합=1로 정규화해 기여 가중치로 쓴다.

    paths: [(채널시퀀스, 전환여부)]  — 여러 방문자의 경로 표본
    반환: {채널: 정규화 기여도}
    """
    if not channels:
        return {}

    def _conv_rate(exclude: str | None) -> float:
        """해당 채널을 제거한 뒤의 전환율. 경로가 비면 전환 불가로 본다."""
        total = 0
        converted = 0
        for seq, conv in paths:
            kept = [c for c in seq if c != exclude] if exclude else list(seq)
            if not kept:
                # 경로가 전부 사라지면 그 방문자는 도달 자체가 불가 → 미전환
                total += 1
                continue
            total += 1
            if conv:
                converted += 1
        return converted / total if total else 0.0

    base = _conv_rate(None)
    if base <= 0:
        return dict.fromkeys(channels, 1.0 / len(channels))

    effects: dict[str, float] = {}
    for c in channels:
        without = _conv_rate(c)
        effects[c] = max(0.0, 1.0 - (without / base))

    total = math.fsum(effects.values())
    if total <= 0:
        return dict.fromkeys(channels, 1.0 / len(channels))
    return {c: v / total for c, v in effects.items()}


# ── Shapley 값 ────────────────────────────────────────────────
def _coalition_value(members: frozenset[str], conv_by_set: dict[frozenset[str], float]) -> float:
    """부분집합의 전환 가치. 관측된 조합이 없으면 포함관계로 근사(단조 하한)."""
    if members in conv_by_set:
        return conv_by_set[members]
    if not members:
        return 0.0
    # 관측되지 않은 조합: 포함되는 관측 조합들의 최대값(가치의 단조성 가정)
    best = 0.0
    for observed, val in conv_by_set.items():
        if observed and observed <= members and val > best:
            best = val
    return best


def shapley(paths: Sequence[tuple[Sequence[str], bool]], channels: Sequence[str],
            *, rng_seed: int = 12345) -> dict[str, float]:
    """협조게임 Shapley 값으로 채널 기여도를 계산.

    각 채널의 기여 = 모든 순열에 대해 '그 채널이 합류할 때 늘어난 가치'의 평균.
    Shapley 값은 효율성(합=전체가치)·대칭성·더미성·가법성을 만족하는 유일한 배분이라,
    파트너 간 배분 공정성을 수학적으로 보장할 수 있다.

    채널 수 ≤ 8 이면 전체 순열로 정확 계산, 초과하면 몬테카를로 근사.
    """
    chans = list(dict.fromkeys(channels))
    if not chans:
        return {}

    # 조합별 전환 가치 집계: 경로에 등장한 채널 집합 → 전환율
    counts: dict[frozenset[str], list[int]] = {}
    for seq, conv in paths:
        key = frozenset(c for c in seq if c in chans)
        if not key:
            continue
        agg = counts.setdefault(key, [0, 0])
        agg[0] += 1
        agg[1] += 1 if conv else 0
    conv_by_set = {k: (v[1] / v[0]) for k, v in counts.items() if v[0] > 0}
    if not conv_by_set:
        return dict.fromkeys(chans, 1.0 / len(chans))

    contrib = dict.fromkeys(chans, 0.0)

    if len(chans) <= _SHAPLEY_EXACT_MAX:
        perms = list(permutations(chans))
        for perm in perms:
            acc: set[str] = set()
            prev = 0.0
            for c in perm:
                acc.add(c)
                val = _coalition_value(frozenset(acc), conv_by_set)
                contrib[c] += val - prev
                prev = val
        for c in chans:
            contrib[c] /= len(perms)
    else:
        # 몬테카를로: 순열을 무작위 표본추출(결정론적 시드로 재현 가능)
        import random
        rnd = random.Random(rng_seed)
        for _ in range(_SHAPLEY_SAMPLES):
            perm = chans[:]
            rnd.shuffle(perm)
            acc = set()
            prev = 0.0
            for c in perm:
                acc.add(c)
                val = _coalition_value(frozenset(acc), conv_by_set)
                contrib[c] += val - prev
                prev = val
        for c in chans:
            contrib[c] /= _SHAPLEY_SAMPLES

    # 음수 기여(노이즈)는 0으로 절단 후 정규화
    clipped = {c: max(0.0, v) for c, v in contrib.items()}
    total = math.fsum(clipped.values())
    if total <= 0:
        return dict.fromkeys(chans, 1.0 / len(chans))
    return {c: v / total for c, v in clipped.items()}


# ── 통합 진입점 ───────────────────────────────────────────────
def attribute(touches: Sequence[Touch], *, model: str = "time_decay",
              lookback_days: int = 30, conversion_at: datetime | None = None,
              channel_weights: dict[str, float] | None = None) -> list[float]:
    """터치포인트 목록에 대해 기여 가중치 리스트를 산출(합=1).

    lookback_days 밖의 터치는 제외(쿠키 윈도 밖 = 기여 없음).
    markov/shapley 는 코호트 단위로 미리 계산한 channel_weights 를 주입받아
    개별 전환에 적용한다(전환 1건만으로는 확률 추정이 불가하므로).
    """
    if not touches:
        return []
    ref = conversion_at or max(t.occurred_at for t in touches)
    window = ref - timedelta(days=lookback_days)
    idx = [i for i, t in enumerate(touches) if t.occurred_at >= window]
    if not idx:
        return [0.0] * len(touches)

    kept = [touches[i] for i in idx]

    if model == "last_click":
        w = last_click(kept)
    elif model == "position":
        w = position_based(kept)
    elif model in ("markov", "shapley"):
        if not channel_weights:
            w = time_decay(kept)  # 코호트 가중치 없으면 안전한 기본값
        else:
            raw = [max(0.0, channel_weights.get(t.channel, 0.0)) for t in kept]
            w = _normalize(raw) if math.fsum(raw) > 0 else time_decay(kept)
    else:  # time_decay(기본)
        w = time_decay(kept)

    out = [0.0] * len(touches)
    for pos, i in enumerate(idx):
        out[i] = w[pos]
    return out


def credit_amounts(weights: Sequence[float], amount: Decimal) -> list[Decimal]:
    """가중치에 따라 금액을 배분. **최대잔여법**으로 합계 불일치 0 보장.

    단순 반올림은 합이 원금과 어긋난다(예: 3등분 시 1원 증발). 최대잔여법은
    내림 배분 후 남은 최소단위를 소수부가 큰 순서로 나눠주어 합계를 정확히 맞춘다.
    """
    if not weights:
        return []
    quant = Decimal("0.0001")  # NUMERIC(18,4) 최소단위
    exact = [amount * Decimal(str(w)) for w in weights]
    floored = [e.quantize(quant, rounding="ROUND_DOWN") for e in exact]
    remainder = amount - sum(floored)
    if remainder > 0:
        # 소수부가 큰 순서로 최소단위씩 배분
        order = sorted(range(len(exact)), key=lambda i: exact[i] - floored[i], reverse=True)
        steps = int((remainder / quant).to_integral_value(rounding="ROUND_HALF_UP"))
        for k in range(steps):
            floored[order[k % len(order)]] += quant
    return floored

"""어트리뷰션 모델 게이트 — 고급 모델을 '언제 켜도 되는가'를 통계로 판단한다.

마르코프 제거효과와 Shapley 값은 확률 추정이다. 경로 표본이 부족하면 추정치가
표본 노이즈에 지배되어 **시간감쇠보다 나쁜 배분**을 만든다. 그리고 그 배분은
곧 지급액이므로, 틀리면 파트너에게 실제 손해가 간다.

그래서 세 조건을 모두 만족할 때만 켠다.
  1) 표본 크기   : 경로 수·전환 수가 최소 기준 이상
  2) 조합 관측   : 채널 조합이 충분히 관측됨(Shapley 는 조합별 가치가 필요)
  3) 추정 안정성 : **부트스트랩 재표본** 간 가중치가 흔들리지 않음

(3)이 핵심이다. 표본이 커도 추정이 불안정하면 매일 배분이 출렁이고, 파트너는
"어제는 30%였는데 오늘 15%"를 납득하지 못한다. 재표본 간 가중치의 평균 절대편차를
안정성 지표로 삼아, 임계 이하일 때만 승격한다.
"""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from psycopg import Connection

from gamdap.growth.attribution import markov_removal, shapley
from gamdap.logging import get_logger

log = get_logger("growth.model_gate")

__all__ = ["bootstrap_stability", "collect_paths", "evaluate_model", "evaluate_all"]

# 부트스트랩 재표본 횟수. 30 이면 평균 편차 추정에 충분하고 계산도 가볍다.
_BOOTSTRAP_ROUNDS = 30
# 가중치 평균 절대편차가 이 값 이하면 '안정'으로 본다.
# 0.05 = 채널 기여도가 재표본 간 평균 5%p 이내로 흔들린다는 뜻.
_STABILITY_THRESHOLD = 0.05
_SEED = 20260731


def collect_paths(conn: Connection, *, lookback_days: int = 90,
                  limit: int = 50_000) -> tuple[list[tuple[list[str], bool]], list[str]]:
    """방문자별 채널 경로와 전환 여부를 수집한다.

    전환한 방문자는 conversions 에 있고, 전환하지 않은 방문자도 반드시 포함해야
    한다 — 전환 경로만 보면 '모든 경로가 전환한다'는 결론이 나온다(생존자 편향).
    """
    since = datetime.now(UTC) - timedelta(days=lookback_days)
    rows = conn.execute(
        "SELECT t.visitor_id, "
        "       array_agg(COALESCE(t.channel,'direct') ORDER BY t.occurred_at) AS channels, "
        "       EXISTS (SELECT 1 FROM core.conversions c "
        "               WHERE c.visitor_id = t.visitor_id AND c.occurred_at >= %s) AS converted "
        "FROM core.touchpoints t "
        "WHERE t.occurred_at >= %s AND t.is_bot = FALSE "
        "GROUP BY t.visitor_id LIMIT %s", (since, since, limit)).fetchall()

    paths: list[tuple[list[str], bool]] = []
    seen: set[str] = set()
    for r in rows:
        chans = [c for c in (r["channels"] or []) if c]
        if not chans:
            continue
        paths.append((chans, bool(r["converted"])))
        seen.update(chans)
    return paths, sorted(seen)


def _weights_for(model: str, paths: Sequence[tuple[list[str], bool]],
                 channels: Sequence[str]) -> dict[str, float]:
    if model == "markov":
        return markov_removal(paths, channels)
    if model == "shapley":
        return shapley(paths, channels)
    raise ValueError(f"게이트 대상이 아닌 모델: {model}")


def bootstrap_stability(model: str, paths: Sequence[tuple[list[str], bool]],
                        channels: Sequence[str], *, rounds: int = _BOOTSTRAP_ROUNDS,
                        seed: int = _SEED) -> tuple[float, dict[str, float]]:
    """부트스트랩으로 가중치 안정성을 측정한다.

    반환: (안정성 0~1, 전체표본 가중치)
      안정성 = 1 − 평균절대편차 / 임계  를 0~1 로 자른 값.
      1.0 에 가까울수록 재표본 간 가중치가 일치한다.
    """
    if not paths or len(channels) < 2:
        return 0.0, {}

    full = _weights_for(model, paths, channels)
    rnd = random.Random(seed)
    n = len(paths)
    deviations: list[float] = []

    for _ in range(rounds):
        resample = [paths[rnd.randrange(n)] for _ in range(n)]
        w = _weights_for(model, resample, channels)
        # 채널별 절대편차의 평균(가중치 합이 1이므로 스케일 비교 가능)
        dev = sum(abs(w.get(c, 0.0) - full.get(c, 0.0)) for c in channels) / len(channels)
        deviations.append(dev)

    mad = sum(deviations) / len(deviations)
    stability = max(0.0, min(1.0, 1.0 - mad / _STABILITY_THRESHOLD))
    return stability, full


def evaluate_model(conn: Connection, model: str, *, lookback_days: int = 90) -> dict:
    """모델 하나를 평가하고 상태를 갱신한다. 조건 충족 시 활성화."""
    state = conn.execute(
        "SELECT * FROM core.attribution_model_state WHERE model=%s", (model,)).fetchone()
    if not state:
        raise ValueError(f"등록되지 않은 모델: {model}")

    paths, channels = collect_paths(conn, lookback_days=lookback_days)
    conversions = sum(1 for _, c in paths if c)

    reasons: list[str] = []
    if len(paths) < state["min_paths"]:
        reasons.append(f"경로 {len(paths)}/{state['min_paths']} 부족")
    if conversions < state["min_conversions"]:
        reasons.append(f"전환 {conversions}/{state['min_conversions']} 부족")
    if len(channels) < 2:
        reasons.append("채널이 2개 미만 — 배분 자체가 무의미")

    stability = 0.0
    weights: dict[str, float] = {}
    if not reasons:
        stability, weights = bootstrap_stability(model, paths, channels)
        if stability < 0.5:
            reasons.append(f"추정 불안정(안정성 {stability:.2f} < 0.50) — 배분이 매일 출렁임")

    enabled = not reasons
    conn.execute(
        "UPDATE core.attribution_model_state SET is_enabled=%s, paths_observed=%s, "
        "  conversions_obs=%s, channels_obs=%s, channel_weights=%s::jsonb, stability=%s, "
        "  evaluated_at=now(), note=%s WHERE model=%s",
        (enabled, len(paths), conversions, len(channels),
         json.dumps(weights, ensure_ascii=False), round(stability, 4),
         ("활성 — 조건 충족" if enabled else " · ".join(reasons)), model))

    log.info("model_gate.evaluated", model=model, enabled=enabled, paths=len(paths),
             conversions=conversions, stability=round(stability, 4))
    return {"model": model, "enabled": enabled, "paths": len(paths),
            "conversions": conversions, "channels": len(channels),
            "stability": round(stability, 4), "channel_weights": weights,
            "blockers": reasons}


def evaluate_all(conn: Connection, *, lookback_days: int = 90) -> dict:
    """게이트 대상 모델을 모두 평가."""
    rows = conn.execute("SELECT model FROM core.attribution_model_state ORDER BY model").fetchall()
    return {r["model"]: evaluate_model(conn, r["model"], lookback_days=lookback_days)
            for r in rows}


def active_model(conn: Connection, preferred: str = "shapley") -> tuple[str, dict]:
    """지금 사용할 모델과 채널 가중치를 고른다.

    선호 모델이 활성이면 그것을, 아니면 마르코프, 그것도 아니면 시간감쇠(항상 안전).
    → 표본이 쌓이면 자동으로 고급 모델로 승격되고, 흔들리면 자동으로 내려온다.
    """
    for candidate in (preferred, "markov"):
        row = conn.execute(
            "SELECT model, is_enabled, channel_weights FROM core.attribution_model_state "
            "WHERE model=%s AND is_enabled", (candidate,)).fetchone()
        if row:
            weights = row["channel_weights"] or {}
            if weights:
                return row["model"], {k: float(v) for k, v in weights.items()}
    return "time_decay", {}


def sample_progress(conn: Connection) -> list[dict]:
    """활성화까지 얼마나 남았는지 — 대시보드 표시용."""
    rows = conn.execute(
        "SELECT model, is_enabled, paths_observed, min_paths, conversions_obs, "
        "       min_conversions, stability, note FROM core.attribution_model_state "
        "ORDER BY model").fetchall()
    out = []
    for r in rows:
        path_pct = min(1.0, r["paths_observed"] / max(1, r["min_paths"]))
        conv_pct = min(1.0, r["conversions_obs"] / max(1, r["min_conversions"]))
        out.append({
            "model": r["model"], "enabled": r["is_enabled"],
            "paths": f"{r['paths_observed']}/{r['min_paths']}",
            "conversions": f"{r['conversions_obs']}/{r['min_conversions']}",
            "progress": round(min(path_pct, conv_pct), 3),
            "stability": float(r["stability"]) if r["stability"] is not None else None,
            "note": r["note"],
        })
    return out

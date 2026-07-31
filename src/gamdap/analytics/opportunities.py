"""변동 감지 엔진(§8.4) — 가격/수수료/재고 시계열에서 '기회' 이벤트 추출.

순수 감지 로직(detect_events)과 DB 잡(scan_opportunities)을 분리해 테스트 가능.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Connection

# 임계값(튜닝 대상)
PRICE_DROP_PCT = 0.10        # 10% 이상 하락
PRICE_Z = 2.0                # 이동평균 대비 z-score
COMMISSION_UP_ABS = 0.02     # 수수료율 2%p 이상 상승


@dataclass
class Obs:
    observed_at: datetime
    price: float | None = None
    commission_rate: float | None = None
    stock_status: str | None = None


@dataclass
class Event:
    kind: str
    severity: str
    detail: dict


def zscore(value: float, series: list[float]) -> float:
    """value 의 series 대비 z-score. 표본<2 또는 표준편차 0이면 0."""
    if len(series) < 2:
        return 0.0
    mean = statistics.fmean(series)
    sd = statistics.pstdev(series)
    if sd == 0:
        return 0.0
    return (value - mean) / sd


def detect_events(obs: list[Obs]) -> list[Event]:
    """시간순 관측값에서 변동 이벤트 목록 산출. 최신 관측을 직전 이력과 비교."""
    if len(obs) < 2:
        return []
    hist, cur = obs[:-1], obs[-1]
    events: list[Event] = []

    # 가격
    prices = [o.price for o in hist if o.price is not None]
    if cur.price is not None and prices:
        prev = prices[-1]
        pct = (cur.price - prev) / prev if prev else 0.0
        z = zscore(cur.price, prices)
        if pct <= -PRICE_DROP_PCT or z <= -PRICE_Z:
            events.append(Event("price_drop", "high" if pct <= -0.2 else "warn",
                                {"from": prev, "to": cur.price, "pct": round(pct, 4), "z": round(z, 3)}))
        elif pct >= PRICE_DROP_PCT or z >= PRICE_Z:
            events.append(Event("price_up", "info",
                                {"from": prev, "to": cur.price, "pct": round(pct, 4), "z": round(z, 3)}))

    # 수수료
    comms = [o.commission_rate for o in hist if o.commission_rate is not None]
    if cur.commission_rate is not None and comms:
        prev_c = comms[-1]
        delta = cur.commission_rate - prev_c
        if delta >= COMMISSION_UP_ABS:
            events.append(Event("commission_up", "high",
                                {"from": prev_c, "to": cur.commission_rate, "delta": round(delta, 4)}))
        elif delta <= -COMMISSION_UP_ABS:
            events.append(Event("commission_down", "info",
                                {"from": prev_c, "to": cur.commission_rate, "delta": round(delta, 4)}))

    # 재고
    prev_stock = next((o.stock_status for o in reversed(hist) if o.stock_status), None)
    if cur.stock_status and cur.stock_status != prev_stock:
        if cur.stock_status == "out_of_stock":
            events.append(Event("stock_out", "warn", {"from": prev_stock, "to": cur.stock_status}))
        elif cur.stock_status == "low":
            events.append(Event("stock_low", "warn", {"from": prev_stock, "to": cur.stock_status}))
        elif cur.stock_status == "in_stock" and prev_stock in ("out_of_stock", "low"):
            events.append(Event("back_in_stock", "info", {"from": prev_stock, "to": cur.stock_status}))

    return events


def scan_opportunities(conn: Connection, lookback_points: int = 10) -> int:
    """최근 이력이 있는 오퍼별로 변동을 감지해 opportunity_events 에 적재. 이벤트 수 반환."""
    offer_ids = [
        r["offer_id"]
        for r in conn.execute(
            "SELECT DISTINCT offer_id FROM core.price_history "
            "WHERE observed_at >= now() - interval '7 days'"
        ).fetchall()
    ]
    total = 0
    for oid in offer_ids:
        rows = conn.execute(
            "SELECT observed_at, price_amount, commission_rate, stock_status "
            "FROM core.price_history WHERE offer_id=%s "
            "ORDER BY observed_at DESC LIMIT %s",
            (oid, lookback_points),
        ).fetchall()
        if len(rows) < 2:
            continue
        obs = [
            Obs(
                observed_at=r["observed_at"],
                price=float(r["price_amount"]) if r["price_amount"] is not None else None,
                commission_rate=float(r["commission_rate"]) if r["commission_rate"] is not None else None,
                stock_status=r["stock_status"],
            )
            for r in reversed(rows)  # 시간 오름차순
        ]
        detected_at = obs[-1].observed_at
        for ev in detect_events(obs):
            import json

            n = conn.execute(
                "INSERT INTO core.opportunity_events (offer_id, kind, severity, detail, detected_at) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (offer_id, kind, detected_at) DO NOTHING",
                (oid, ev.kind, ev.severity, json.dumps(ev.detail, ensure_ascii=False), detected_at),
            ).rowcount
            total += n
    return total

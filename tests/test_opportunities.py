"""변동 감지 엔진 테스트(§8.4, M7)."""

from datetime import UTC, datetime, timedelta

from gamdap.analytics.opportunities import Obs, detect_events, zscore

T0 = datetime(2026, 7, 1, tzinfo=UTC)


def _series(prices=None, comms=None, stocks=None) -> list[Obs]:
    n = max(len(prices or []), len(comms or []), len(stocks or []))
    out = []
    for i in range(n):
        out.append(Obs(
            observed_at=T0 + timedelta(days=i),
            price=(prices[i] if prices else None),
            commission_rate=(comms[i] if comms else None),
            stock_status=(stocks[i] if stocks else None),
        ))
    return out


def test_zscore_basic():
    assert zscore(10, [10, 10]) == 0.0        # sd=0
    assert zscore(5, [1]) == 0.0              # 표본<2
    z = zscore(0, [10, 10, 10, 10])           # sd=0 → 0
    assert z == 0.0


def test_price_drop_detected():
    evs = detect_events(_series(prices=[10000, 10000, 10000, 8000]))
    kinds = {e.kind for e in evs}
    assert "price_drop" in kinds
    ev = next(e for e in evs if e.kind == "price_drop")
    assert ev.detail["to"] == 8000


def test_price_drop_high_severity_over_20pct():
    evs = detect_events(_series(prices=[100, 100, 100, 70]))  # -30%
    ev = next(e for e in evs if e.kind == "price_drop")
    assert ev.severity == "high"


def test_no_event_when_stable():
    assert detect_events(_series(prices=[100, 101, 99, 100])) == []


def test_commission_increase_high():
    evs = detect_events(_series(comms=[0.03, 0.03, 0.03, 0.15]))  # 기획전 3%→15%
    ev = next(e for e in evs if e.kind == "commission_up")
    assert ev.severity == "high"
    assert ev.detail["to"] == 0.15


def test_stock_out_transition():
    evs = detect_events(_series(stocks=["in_stock", "in_stock", "low", "out_of_stock"]))
    assert any(e.kind == "stock_out" for e in evs)


def test_back_in_stock():
    evs = detect_events(_series(stocks=["out_of_stock", "out_of_stock", "in_stock"]))
    assert any(e.kind == "back_in_stock" for e in evs)


def test_single_obs_no_events():
    assert detect_events(_series(prices=[100])) == []

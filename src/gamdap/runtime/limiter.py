"""부하 안정화 프리미티브(순수, 시각 주입 가능 → 결정론적 테스트).

TokenBucket   : 초당 refill_rate 로 채워지는 버킷. 대량 호출을 부드럽게 shaping.
CircuitBreaker: 연속 실패 시 open → 일정 시간 후 half_open → 성공 시 closed.
ConnectorGuard: 커넥터별 (레이트리밋 + 서킷) 결합. 대량 크롤 시 폭주·장애 격리.

프로세스 내 in-memory. 분산(다중 워커)은 Redis 백엔드로 교체(동일 인터페이스).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

Clock = Callable[[], float]


class TokenBucket:
    """토큰버킷 레이트리미터. capacity 개까지 버스트 허용, refill_rate/s 로 재충전."""

    def __init__(self, rate_per_sec: float, capacity: float | None = None,
                 clock: Clock = time.monotonic) -> None:
        self.rate = float(rate_per_sec)
        self.capacity = float(capacity if capacity is not None else max(rate_per_sec, 1.0))
        self._tokens = self.capacity
        self._clock = clock
        self._last = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last = now

    def try_acquire(self, n: float = 1.0) -> bool:
        """즉시 획득 시도. 성공 True."""
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False

    def acquire(self, n: float = 1.0, timeout: float | None = None) -> bool:
        """토큰 확보까지 대기(최대 timeout). 성공 True."""
        deadline = None if timeout is None else self._clock() + timeout
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= n:
                    self._tokens -= n
                    return True
                wait = (n - self._tokens) / self.rate if self.rate > 0 else 0.05
            if deadline is not None and self._clock() + wait > deadline:
                return False
            time.sleep(min(wait, 0.5))

    @property
    def available(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


class CircuitState(StrEnum):
    CLOSED = "closed"       # 정상
    OPEN = "open"           # 차단(장애)
    HALF_OPEN = "half_open"  # 시험 통과 대기


class CircuitBreaker:
    """서킷브레이커. 연속 실패 threshold 도달 시 open, recovery 후 half_open 시험."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0,
                 half_open_max: int = 2, clock: Clock = time.monotonic) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_half_open()
            return self._state

    def _maybe_half_open(self) -> None:
        if self._state == CircuitState.OPEN and \
           self._clock() - self._opened_at >= self.recovery_timeout:
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 0

    def allow(self) -> bool:
        """호출 허용 여부. open이면 차단(단, recovery 지나면 half_open 시험 허용)."""
        with self._lock:
            self._maybe_half_open()
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max:
                    self._half_open_calls += 1
                    return True
                return False
            return False  # OPEN

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._state == CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()


@dataclass
class ConnectorGuard:
    """커넥터별 부하 가드 = 토큰버킷 + 서킷브레이커."""

    bucket: TokenBucket
    breaker: CircuitBreaker
    stats: dict = field(default_factory=lambda: {"allowed": 0, "throttled": 0, "short_circuited": 0})

    def before(self, timeout: float = 30.0) -> bool:
        """호출 전 게이트. 서킷 open이면 즉시 False, 아니면 토큰 확보까지 대기."""
        if not self.breaker.allow():
            self.stats["short_circuited"] += 1
            return False
        if not self.bucket.acquire(timeout=timeout):
            self.stats["throttled"] += 1
            return False
        self.stats["allowed"] += 1
        return True

    def success(self) -> None:
        self.breaker.record_success()

    def failure(self) -> None:
        self.breaker.record_failure()


# 커넥터 코드별 가드 레지스트리(프로세스 내)
_GUARDS: dict[str, ConnectorGuard] = {}
_GUARDS_LOCK = threading.Lock()


def get_guard(code: str, rate_per_sec: float = 1.0, capacity: float | None = None,
              failure_threshold: int = 5, recovery_timeout: float = 30.0) -> ConnectorGuard:
    """커넥터별 가드 확보(없으면 생성). 대량 크롤 시 커넥터마다 독립 shaping·격리."""
    with _GUARDS_LOCK:
        g = _GUARDS.get(code)
        if g is None:
            g = ConnectorGuard(
                bucket=TokenBucket(rate_per_sec, capacity),
                breaker=CircuitBreaker(failure_threshold, recovery_timeout),
            )
            _GUARDS[code] = g
        return g

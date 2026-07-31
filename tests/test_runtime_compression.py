"""부하 안정화(토큰버킷·서킷브레이커) + 압축(zstd) 테스트."""


from gamdap.runtime.limiter import CircuitBreaker, CircuitState, TokenBucket
from gamdap.storage.compression import (
    compress,
    compress_json,
    decompress,
    decompress_json,
    ratio,
    train_dictionary,
)


# ── 토큰버킷 (시각 주입 결정론) ──
def test_token_bucket_burst_then_throttle():
    t = [0.0]
    tb = TokenBucket(rate_per_sec=10, capacity=5, clock=lambda: t[0])
    # 초기 버킷 5개 → 5회 즉시 성공, 6번째 실패
    assert sum(tb.try_acquire() for _ in range(5)) == 5
    assert tb.try_acquire() is False


def test_token_bucket_refill():
    t = [0.0]
    tb = TokenBucket(rate_per_sec=10, capacity=5, clock=lambda: t[0])
    for _ in range(5):
        tb.try_acquire()
    assert tb.try_acquire() is False
    t[0] = 0.5  # 0.5초 → 5토큰 재충전
    assert tb.try_acquire() is True


# ── 서킷브레이커 ──
def test_circuit_opens_after_threshold():
    t = [0.0]
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10, clock=lambda: t[0])
    assert cb.allow() is True
    for _ in range(3):
        cb.record_failure()
    assert cb.state is CircuitState.OPEN
    assert cb.allow() is False


def test_circuit_half_open_then_close():
    t = [0.0]
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10, half_open_max=1, clock=lambda: t[0])
    cb.record_failure()
    cb.record_failure()
    assert cb.state is CircuitState.OPEN
    t[0] = 11  # recovery 경과 → half_open
    assert cb.allow() is True                # 시험 호출 허용
    cb.record_success()
    assert cb.state is CircuitState.CLOSED   # 성공 → 복구


def test_circuit_half_open_fail_reopens():
    t = [0.0]
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10, half_open_max=1, clock=lambda: t[0])
    cb.record_failure()
    cb.record_failure()
    t[0] = 11
    cb.allow()
    cb.record_failure()                      # 시험 실패 → 재개방
    assert cb.state is CircuitState.OPEN


# ── zstd 압축 ──
def test_compress_roundtrip():
    data = b"hello " * 1000
    blob = compress(data)
    assert decompress(blob) == data
    assert ratio(data, blob) > 5             # 반복 데이터 고압축


def test_compress_json_roundtrip():
    obj = {"products": [{"id": i, "title": f"item {i}", "price": i * 1.5} for i in range(50)]}
    blob = compress_json(obj)
    assert decompress_json(blob) == obj


def test_dictionary_beats_plain_on_similar_payloads():
    # 유사 구조 소형 payload → 딕셔너리 압축이 개별 압축보다 우수
    samples = [
        f'{{"id":{i},"title":"Product {i}","price":{i}.99,"stock":{i*3},"category":"electronics"}}'.encode()
        for i in range(20)
    ]
    d = train_dictionary(samples, dict_size=4096)
    one = samples[0]
    plain = compress(one)
    withdict = compress(one, dictionary=d)
    assert decompress(withdict, dictionary=d) == one
    assert len(withdict) < len(plain)        # 딕셔너리가 더 작게


def test_ratio():
    assert ratio(b"x" * 100, b"x" * 10) == 10.0

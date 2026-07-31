"""AI 어시스트 프레임워크 테스트(M6) — 어댑터·레지스트리·예산 가드·텍스트벡터."""

from gamdap.ai.adapter import CAPABILITIES, AIAssistAdapter
from gamdap.ai.adapters.local_heuristic import LocalHeuristicAdapter
from gamdap.ai.registry import build_adapter, known_adapters
from gamdap.ai.router import within_budget
from gamdap.textvec import cosine, hashing_embedding, softmax, tokenize


def test_local_adapter_conforms_protocol():
    a = LocalHeuristicAdapter()
    assert isinstance(a, AIAssistAdapter)          # runtime_checkable protocol
    assert a.supports() <= CAPABILITIES
    assert a.health().ok
    assert a.unit_cost() == 0.0


def test_local_category_mapping():
    a = LocalHeuristicAdapter()
    sug = a.run("category_mapping", {"raw_name": "주방가전"})
    assert sug.data["slug"] == "electronics.appliance"
    assert sug.confidence > 0


def test_local_embedding_deterministic():
    a = LocalHeuristicAdapter()
    s1 = a.run("embedding", {"text": "무선 이어폰"})
    s2 = a.run("embedding", {"text": "무선 이어폰"})
    assert s1.data["embedding"] == s2.data["embedding"]      # 결정론
    assert s1.data["dim"] == 64


def test_local_trend_signal_rank_monotonic():
    a = LocalHeuristicAdapter()
    top = a.run("trend_signal", {"native_rank": 1, "max_rank": 100}).data["trend"]
    low = a.run("trend_signal", {"native_rank": 100, "max_rank": 100}).data["trend"]
    assert top > low


def test_registry_build():
    assert "local_heuristic" in known_adapters()
    a = build_adapter("local_heuristic", {"embedding_dim": 32})
    assert a.run("embedding", {"text": "x"}).data["dim"] == 32


def test_within_budget():
    assert within_budget(5.0, None) is True           # 무제한
    assert within_budget(4.0, 10.0) is True
    assert within_budget(10.0, 10.0) is False         # 초과 시 차단


def test_textvec_cosine_identity():
    v = hashing_embedding("same text")
    assert cosine(v, v) == 1.0 or abs(cosine(v, v) - 1.0) < 1e-9


def test_textvec_similar_more_than_dissimilar():
    base = hashing_embedding("무선 블루투스 이어폰")
    sim = hashing_embedding("무선 블루투스 이어폰 프로")
    dis = hashing_embedding("강아지 사료 대용량")
    assert cosine(base, sim) > cosine(base, dis)


def test_softmax_sums_to_one():
    p = softmax([1.0, 2.0, 3.0])
    assert abs(sum(p) - 1.0) < 1e-9
    assert p[2] > p[0]


def test_tokenize():
    assert tokenize("Hello 월드 123!") == ["hello", "월드", "123"]

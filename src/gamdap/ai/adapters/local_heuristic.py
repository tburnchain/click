"""로컬 휴리스틱 어댑터(레퍼런스) — 외부 API 없이 결정론적으로 동작.

프레임워크(레지스트리·라우터·제안 큐)를 네트워크 없이 검증하기 위한 기본 어댑터.
실제 운영에서는 OpenAI 호환/로컬 LLM/자체 크롤추적 어댑터로 교체·병행한다.
비용 0(온프레미스 계산).
"""

from __future__ import annotations

from gamdap.ai.adapter import AISuggestion, HealthStatus
from gamdap.normalize.category_map import map_category
from gamdap.textvec import hashing_embedding


class LocalHeuristicAdapter:
    code = "local_heuristic"

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self.dim = int(self.config.get("embedding_dim", 64))

    def supports(self) -> set[str]:
        return {"category_mapping", "embedding", "trend_signal"}

    def run(self, capability: str, payload: dict) -> AISuggestion:
        if capability == "category_mapping":
            slug, conf = map_category(payload.get("raw_name"))
            return AISuggestion(data={"slug": slug}, confidence=conf)

        if capability == "embedding":
            text = payload.get("text", "")
            vec = hashing_embedding(text, self.dim)
            return AISuggestion(data={"embedding": vec, "dim": self.dim}, confidence=1.0)

        if capability == "trend_signal":
            # native_rank 를 0~1 신호로(낮은 랭크=높은 트렌드). 결정론적.
            rank = payload.get("native_rank")
            max_rank = max(int(payload.get("max_rank", 100)), 1)
            if rank is None:
                return AISuggestion(data={"trend": 0.5}, confidence=0.3)
            trend = max(0.0, 1.0 - (min(int(rank), max_rank) - 1) / max_rank)
            return AISuggestion(data={"trend": round(trend, 4)}, confidence=0.6)

        return AISuggestion(data={"error": f"unsupported: {capability}"}, confidence=0.0)

    def health(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="local heuristic ready")

    def unit_cost(self) -> float:
        return 0.0

"""AI 어댑터 규격(§7.3) — 벤더 중립. 어떤 제공자든 이 규격만 구현하면 장착."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# 지원 역량 슬롯(DB CHECK 제약과 정합)
CAPABILITIES = frozenset({
    "category_mapping", "entity_matching", "translation",
    "trend_signal", "crawl_assist", "change_tracking", "embedding", "discovery",
})


@dataclass
class AISuggestion:
    """어댑터 산출물. 코어에 직접 쓰지 않고 ai_suggestions(pending)로만 저장된다."""

    data: dict = field(default_factory=dict)
    confidence: float = 0.5


@dataclass
class HealthStatus:
    ok: bool
    detail: str = ""


@runtime_checkable
class AIAssistAdapter(Protocol):
    code: str

    def supports(self) -> set[str]: ...
    def run(self, capability: str, payload: dict) -> AISuggestion: ...
    def health(self) -> HealthStatus: ...
    def unit_cost(self) -> float: ...

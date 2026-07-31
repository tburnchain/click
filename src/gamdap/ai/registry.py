"""어댑터 레지스트리 — adapter 코드 → 어댑터 인스턴스."""

from __future__ import annotations

from collections.abc import Callable

from gamdap.ai.adapter import AIAssistAdapter
from gamdap.ai.adapters.local_heuristic import LocalHeuristicAdapter

_REGISTRY: dict[str, Callable[[dict], AIAssistAdapter]] = {}


def register_adapter(code: str, factory: Callable[[dict], AIAssistAdapter]) -> None:
    _REGISTRY[code] = factory


def build_adapter(code: str, config: dict | None = None) -> AIAssistAdapter:
    if code not in _REGISTRY:
        raise KeyError(f"등록되지 않은 AI 어댑터: {code!r}")
    return _REGISTRY[code](config or {})


def known_adapters() -> list[str]:
    return sorted(_REGISTRY)


register_adapter("local_heuristic", lambda cfg: LocalHeuristicAdapter(cfg))

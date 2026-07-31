"""AI 어시스트 플레인(§7, 플러그형·관리자 제어·기본 OFF)."""

from gamdap.ai.adapter import AIAssistAdapter, AISuggestion, HealthStatus
from gamdap.ai.router import route_capability, within_budget

__all__ = [
    "AISuggestion",
    "AIAssistAdapter",
    "HealthStatus",
    "route_capability",
    "within_budget",
]

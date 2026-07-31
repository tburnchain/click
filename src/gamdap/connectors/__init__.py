"""공식 API 커넥터."""

from gamdap.connectors.base import BaseConnector, RateLimit, TermsPolicy
from gamdap.connectors.registry import get_connector, register

__all__ = ["BaseConnector", "RateLimit", "TermsPolicy", "get_connector", "register"]

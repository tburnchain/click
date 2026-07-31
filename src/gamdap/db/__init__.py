"""DB 접근 계층."""

from gamdap.db.pool import get_pool, transaction

__all__ = ["get_pool", "transaction"]

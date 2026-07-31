"""커넥터 공통 인터페이스(설계 §6.1). 모든 네트워크 커넥터가 구현."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime

from gamdap.domain.schemas import RawOffer


@dataclass(frozen=True)
class RateLimit:
    """토큰버킷 파라미터. 커넥터별 호출 한도."""

    requests_per_minute: int = 60
    burst: int = 10


@dataclass(frozen=True)
class TermsPolicy:
    """약관 정책의 코드화(설계 §6.1). 스크래핑 금지 네트워크 차단 근거."""

    scraping_allowed: bool = False
    official_api_only: bool = True
    deeplink_required: bool = True
    notes: str = ""


@dataclass
class FetchResult:
    """수집 1회 결과 + Bronze 적재를 위한 원본."""

    offers: list[RawOffer] = field(default_factory=list)
    raw_request: dict = field(default_factory=dict)
    raw_response: dict | None = None
    http_status: int | None = None
    cost_usd: float = 0.0


class BaseConnector:
    """추상 커넥터. 하위 클래스는 code/adapter 와 fetch_* 를 구현한다."""

    code: str = "base"
    adapter: str = "base"

    def rate_limit(self) -> RateLimit:
        return RateLimit()

    def terms_policy(self) -> TermsPolicy:
        return TermsPolicy()

    def fetch_offers(
        self, *, keyword: str | None = None, category: str | None = None,
        limit: int = 50, since: datetime | None = None,
    ) -> Iterator[FetchResult]:
        """오퍼 배치를 순회 산출. 페이지네이션은 구현체가 처리."""
        raise NotImplementedError

    def health(self) -> bool:
        """자격증명·연결 확인."""
        raise NotImplementedError

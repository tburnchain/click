"""FastAPI 의존성. 테스트는 app.dependency_overrides[get_repo] 로 Fake 주입."""

from __future__ import annotations

from gamdap.api.repo import PgRepo, Repo

_repo: Repo | None = None


def get_repo() -> Repo:
    global _repo
    if _repo is None:
        _repo = PgRepo()
    return _repo

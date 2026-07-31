"""크롤링/수집 관리 API — 커넥터 상태·수집 실행·작업 이력(§ 크롤링 관리 콘솔)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from gamdap.api.deps import get_repo
from gamdap.api.repo import Repo
from gamdap.api.schemas import ConnectorOut, JobOut

router = APIRouter(prefix="/api/v1/crawl", tags=["crawl-admin"])


class IngestIn(BaseModel):
    network: str
    keyword: str | None = None
    limit: int = Field(30, ge=1, le=100)


@router.get("/connectors", response_model=list[ConnectorOut])
def connectors(repo: Repo = Depends(get_repo)) -> list[ConnectorOut]:
    return repo.connectors()


@router.get("/jobs", response_model=list[JobOut])
def jobs(limit: int = Query(30, ge=1, le=200), repo: Repo = Depends(get_repo)) -> list[JobOut]:
    return repo.jobs(limit)


@router.post("/ingest", response_model=JobOut)
def run_ingest(body: IngestIn, repo: Repo = Depends(get_repo)) -> JobOut:
    """수집 실행. 실제 커넥터로 즉시 수집하고 작업 요약을 반환한다."""
    return repo.trigger_ingest(body.network, body.keyword, body.limit)

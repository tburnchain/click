"""발견 관리 API(§16 admin) — 후보 검토·온보딩, UCB arm 상태."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gamdap.db import transaction
from gamdap.discovery.scanner import next_arm, onboard_candidate, reject_candidate

router = APIRouter(prefix="/api/v1/discovery", tags=["discovery-admin"])


class OnboardIn(BaseModel):
    adapter: str | None = None


@router.get("/candidates")
def list_candidates(status: str = "pending", limit: int = 100) -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            "SELECT id, name, home_url, country_iso, has_official_api, has_product_feed, "
            "terms_scrape_allowed, candidate_score, status, created_at "
            "FROM core.network_candidates WHERE status=%s "
            "ORDER BY candidate_score DESC LIMIT %s",
            (status, min(limit, 500)),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/candidates/{candidate_id}/onboard")
def onboard(candidate_id: int, body: OnboardIn) -> dict:
    with transaction() as conn:
        net_id = onboard_candidate(conn, candidate_id, adapter=body.adapter)
    if net_id is None:
        raise HTTPException(404, "candidate not found or not onboardable")
    return {"candidate_id": candidate_id, "network_id": net_id}


@router.post("/candidates/{candidate_id}/reject")
def reject(candidate_id: int) -> dict:
    with transaction() as conn:
        ok = reject_candidate(conn, candidate_id)
    if not ok:
        raise HTTPException(404, "candidate not found")
    return {"candidate_id": candidate_id, "status": "rejected"}


@router.get("/next-arm")
def get_next_arm() -> dict:
    """다음에 크롤할 (네트워크×카테고리) arm — UCB 최댓값."""
    with transaction() as conn:
        arm = next_arm(conn)
    return {"arm": arm}

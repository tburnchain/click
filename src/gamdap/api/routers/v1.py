"""v1 REST 라우터(§9.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from gamdap.api.deps import get_repo
from gamdap.api.repo import OfferFilters, Repo
from gamdap.api.schemas import (
    CategoryOut,
    HistoryPoint,
    NetworkOut,
    OfferListOut,
    OfferOut,
    OpportunityOut,
    SummaryOut,
)

router = APIRouter(prefix="/api/v1")


@router.get("/offers", response_model=OfferListOut)
def list_offers(
    network: str | None = None,
    country: str | None = None,
    category: str | None = None,
    billing_type: str | None = None,
    offer_type: str | None = Query(
        None, pattern="^(physical_product|digital_product|app_install|subscription|service|lead|coupon)$"),
    segment: str | None = Query(None, pattern="^(goldmine|rising|cashcow|saturated|avoid)$"),
    min_price: float | None = None,
    max_price: float | None = None,
    q: str | None = None,
    sort: str = Query("score", pattern="^(relevance|score|epc|commission|price|freshness)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    repo: Repo = Depends(get_repo),
) -> OfferListOut:
    return repo.list_offers(OfferFilters(
        network=network, country=country, category=category, billing_type=billing_type,
        offer_type=offer_type, segment=segment, min_price=min_price, max_price=max_price,
        q=q, sort=sort, page=page, size=size,
    ))


@router.get("/offers/{offer_id}", response_model=OfferOut)
def get_offer(offer_id: int, repo: Repo = Depends(get_repo)) -> OfferOut:
    offer = repo.get_offer(offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    return offer


@router.get("/rankings", response_model=list[OfferOut])
def rankings(
    category: str | None = None, country: str | None = None,
    limit: int = Query(50, ge=1, le=100), repo: Repo = Depends(get_repo),
) -> list[OfferOut]:
    return repo.rankings(category, country, limit)


@router.get("/products/{product_id}/offers", response_model=list[OfferOut])
def product_offers(product_id: int, repo: Repo = Depends(get_repo)) -> list[OfferOut]:
    return repo.product_offers(product_id)


@router.get("/compare", response_model=list[OfferOut])
def compare(product_id: int, repo: Repo = Depends(get_repo)) -> list[OfferOut]:
    """동일 상품의 네트워크별 오퍼 비교(수익성 내림차순)."""
    return repo.product_offers(product_id)


@router.get("/analytics/summary", response_model=SummaryOut)
def summary(repo: Repo = Depends(get_repo)) -> SummaryOut:
    return repo.summary()


@router.get("/analytics/opportunities", response_model=list[OpportunityOut])
def opportunities(limit: int = Query(50, ge=1, le=200), repo: Repo = Depends(get_repo)) -> list[OpportunityOut]:
    return repo.opportunities(limit)


@router.get("/offers/{offer_id}/history", response_model=list[HistoryPoint])
def offer_history(
    offer_id: int, limit: int = Query(90, ge=1, le=500), repo: Repo = Depends(get_repo),
) -> list[HistoryPoint]:
    return repo.offer_history(offer_id, limit)


@router.get("/meta/networks", response_model=list[NetworkOut])
def meta_networks(repo: Repo = Depends(get_repo)) -> list[NetworkOut]:
    return repo.networks()


@router.get("/meta/categories", response_model=list[CategoryOut])
def meta_categories(repo: Repo = Depends(get_repo)) -> list[CategoryOut]:
    return repo.categories()

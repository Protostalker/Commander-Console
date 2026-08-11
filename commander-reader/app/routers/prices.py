"""
GET /prices, /prices/live, /prices/history -- all read-only.

There is deliberately no POST/PUT/PATCH here and no import of anything
resembling a price-write helper. Price changes are only ever *detected*
(by diffing successive polls) and logged locally, never written back to
Commander.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from .. import history
from ..models import PriceHistoryRecord, PricesResponse
from ..naxml_parser import parse_fuel_prices

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prices", tags=["prices"])


async def _fetch_and_update(state) -> list:
    """Fetch fresh prices, diff against cache for history, then update cache."""
    xml = await state.commander_client.get_fuel_prices()
    grades = parse_fuel_prices(xml)
    old_grades = state.price_cache.grades
    await history.record_price_changes(state.settings.db_path, old_grades, grades)
    state.price_cache.set(grades)
    state.connection_healthy = True
    return grades


@router.get("", response_model=PricesResponse, summary="Get cached fuel prices")
async def get_prices(request: Request):
    """
    Current fuel prices (In-Effect + Pending), served from the in-memory
    cache refreshed on the poll interval. Use /prices/live to bypass it.
    """
    state = request.app.state
    cache = state.price_cache

    if cache.grades is None:
        # Nothing cached yet (e.g. Commander was down at startup) -- try once now.
        try:
            grades = await _fetch_and_update(state)
        except Exception as e:
            logger.error("No cached prices and live fetch failed: %s", e)
            raise HTTPException(status_code=502, detail=f"No cached prices available: {e}") from e
        return PricesResponse(
            grades=grades, from_cache=False,
            fetched_at=cache.fetched_at, cache_age_seconds=cache.age_seconds(), stale=False,
        )

    return PricesResponse(
        grades=cache.grades,
        from_cache=True,
        fetched_at=cache.fetched_at,
        cache_age_seconds=cache.age_seconds(),
        stale=not cache.is_fresh(),
    )


@router.get("/live", response_model=PricesResponse, summary="Force-fetch prices directly from Commander")
async def get_prices_live(request: Request):
    """Bypass the cache and fetch directly from Commander (slower)."""
    state = request.app.state
    try:
        grades = await _fetch_and_update(state)
    except Exception as e:
        logger.error("Live price fetch failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Commander error: {e}") from e

    return PricesResponse(
        grades=grades,
        from_cache=False,
        fetched_at=state.price_cache.fetched_at,
        cache_age_seconds=0.0,
        stale=False,
    )


@router.get("/history", response_model=list[PriceHistoryRecord], summary="Price change history log")
async def get_history(
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Locally detected price changes, newest first. No Commander round-trip."""
    state = request.app.state
    return await history.get_history(state.settings.db_path, limit=limit, offset=offset)

"""GET /totals -- sales totals aggregated across all dispensers."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from ..models import TotalsResponse
from ..naxml_parser import parse_fuel_totals

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/totals", tags=["totals"])

PERIOD_NAME_TO_NUM = {"shift": 1, "day": 2, "month": 3, "year": 4}


@router.get("", response_model=TotalsResponse, summary="Sales totals aggregated across all dispensers")
async def get_totals(
    request: Request,
    period: str = Query("day", pattern="^(shift|day|month|year)$", description="shift, day, month, or year"),
):
    state = request.app.state
    period_num = PERIOD_NAME_TO_NUM[period]

    try:
        xml = await state.commander_client.get_fuel_totals(period=period_num)
        totals = parse_fuel_totals(xml, period_name=period)
    except Exception as e:
        logger.error("vfueltotals (period=%s) failed: %s", period, e)
        raise HTTPException(status_code=502, detail=f"Commander error: {e}") from e

    return totals

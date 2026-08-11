"""
GET /pumps -- per-pump, per-hose lifetime mechanical totals (vmaintfprht).

NOTE: parse_pump_totals() in naxml_parser.py is unverified against live
Commander hardware (see its docstring). If this endpoint returns a 502
with "Could not parse any pump records", check the container logs for the
raw XML and adjust the tag-name guesses in parse_pump_totals().
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from ..models import PumpsResponse
from ..naxml_parser import parse_pump_totals

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pumps", tags=["pumps"])


@router.get("", response_model=PumpsResponse, summary="Per-pump, per-hose lifetime mechanical totals")
async def get_pumps(request: Request):
    state = request.app.state
    try:
        xml = await state.commander_client.get_pump_totals()
        pumps = parse_pump_totals(xml)
    except Exception as e:
        logger.error("vmaintfprht failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Commander error: {e}") from e

    return pumps

"""GET /config -- fuel site configuration, returned as raw XML for now."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from ..models import ConfigResponse
from ..naxml_parser import extract_site_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=ConfigResponse, summary="Fuel site configuration (raw XML)")
async def get_config(request: Request):
    """
    Returns the raw vfuelcfg XML. The fuelcfg schema (grades, UOM, service
    levels, tier-2 scheduling) isn't fully parsed yet -- a future version
    can turn this into structured JSON once the schema is documented.
    """
    state = request.app.state
    try:
        xml = await state.commander_client.get_fuel_config()
    except Exception as e:
        logger.error("vfuelcfg failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Commander error: {e}") from e

    return ConfigResponse(site_id=extract_site_id(xml), raw_xml=xml)

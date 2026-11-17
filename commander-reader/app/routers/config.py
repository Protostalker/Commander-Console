"""GET /config -- fuel site configuration, returned as raw XML for now.
POST /config/credentials -- live Commander login rotation (see module
docstring on credentials_store.py for why this exists)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Request

from .. import credentials_store
from ..models import ConfigResponse, CredentialsUpdateRequest, CredentialsUpdateResponse
from ..naxml_parser import extract_site_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/config", tags=["config"])


def _check_api_key(settings, provided: str | None) -> None:
    """Guards POST /config/credentials only -- see Settings.config_api_key.
    No-op (open) if CONFIG_API_KEY isn't set, matching this service's
    existing LAN-trust model for every other (read-only) route."""
    if not settings.config_api_key:
        return
    if provided != settings.config_api_key:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")


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


@router.post(
    "/credentials",
    response_model=CredentialsUpdateResponse,
    summary="Update the Commander login this service uses, live, no restart",
)
async def update_credentials(
    request: Request,
    body: CredentialsUpdateRequest,
    x_api_key: str | None = Header(default=None),
):
    """
    Call this right after rotating the password on the Commander console
    itself. Clears the login circuit breaker (see commander_client.py),
    persists the new credentials to this service's own data volume (never
    to the repo or .env), and makes one validating login attempt so you
    find out immediately whether it worked -- not on the next poll cycle.

    That one validating attempt still counts against the Commander's own
    login-attempt limit, so double-check what you typed before calling this
    if the unit is already close to locked out.

    If CONFIG_API_KEY is set, requires a matching X-API-Key header -- the
    one write operation in this read-only service, so it doesn't share the
    rest of the API's no-auth-on-a-trusted-LAN stance unconditionally.
    """
    state = request.app.state
    client = state.commander_client
    settings = state.settings
    _check_api_key(settings, x_api_key)

    username = (body.username or client.username).strip()
    password = body.password

    client.update_credentials(username, password)
    credentials_store.save(settings.db_path, username, password)

    ok = await client.login()
    return CredentialsUpdateResponse(
        ok=ok,
        username=username,
        error=None if ok else client.last_error,
    )

"""
/api/credentials router -- live Commander login rotation.

See credentials_store.py's module docstring for why this exists (the short
version: a password rotated on the Commander console itself shouldn't
require editing a file and restarting this container every time, and the
login circuit breaker in commander_client.py needs some way to be cleared
other than "wait," since a stale password doesn't fix itself).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Request

import credentials_store
from models import CredentialsUpdateRequest, CredentialsUpdateResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/credentials", tags=["credentials"])


def _check_api_key(request: Request, provided: str | None) -> None:
    """No-op if CONFIG_API_KEY isn't set -- see main.py's app.state.config_api_key
    and README's "No authentication" section for why this is opt-in."""
    expected = request.app.state.config_api_key
    if not expected:
        return
    if provided != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")


@router.post(
    "",
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
    itself. Clears the login circuit breaker, persists the new credentials
    to this service's own data volume (never to the repo, commander.yaml,
    or .env), and makes one validating login attempt so you find out
    immediately whether it worked.

    That one validating attempt still counts against the Commander's own
    login-attempt limit, so double-check what you typed before calling this
    if the unit is already close to locked out.

    If CONFIG_API_KEY is set, requires a matching X-API-Key header.
    """
    state = request.app.state
    _check_api_key(request, x_api_key)

    if state.mock_mode:
        raise HTTPException(
            status_code=400,
            detail="Running in mock mode (commander.yaml: mock.enabled) -- there's no real "
                   "Commander connection to update credentials for.",
        )

    client = state.commander_client
    username = (body.username or client.username).strip()
    password = body.password

    client.update_credentials(username, password)
    credentials_store.save(username, password)

    ok = await client.login()
    return CredentialsUpdateResponse(
        ok=ok,
        username=username,
        error=None if ok else client.last_error,
    )

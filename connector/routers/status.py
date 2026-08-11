"""
/api/status router — connection health and session info.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from models import StatusResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("", response_model=StatusResponse, summary="Commander connection status")
async def get_status(request: Request):
    """
    Return connection health, last sync metadata, and session token age.

    - connected: whether the last communication with Commander succeeded
    - mock_mode: true if running without real hardware
    - commander_host: the configured Commander hostname/IP
    - last_sync: UTC timestamp of most recent successful price fetch
    - last_sync_age_seconds: seconds since last sync
    - session_authenticated: whether a valid session token is held
    - session_token_age_seconds: age of current session token in seconds
    - error: most recent error string (null if healthy)
    """
    state = request.app.state

    if state.mock_mode:
        return StatusResponse(
            connected=True,
            mock_mode=True,
            commander_host=state.config.commander.host,
            last_sync=state.price_cache.last_sync,
            last_sync_age_seconds=state.price_cache.last_sync_age_seconds(),
            session_authenticated=True,
            session_token_age_seconds=None,
            error=None,
        )

    client = state.commander_client
    connected = state.connection_healthy

    return StatusResponse(
        connected=connected,
        mock_mode=False,
        commander_host=state.config.commander.host,
        last_sync=state.price_cache.last_sync,
        last_sync_age_seconds=state.price_cache.last_sync_age_seconds(),
        session_authenticated=client.is_authenticated,
        session_token_age_seconds=(
            client.token_age_seconds if client.is_authenticated else None
        ),
        error=client.last_error if not connected else None,
    )

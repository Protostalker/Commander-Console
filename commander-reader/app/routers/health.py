"""GET /health -- service health and Commander connection status."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health and Commander connection status")
async def health(request: Request):
    state = request.app.state
    client = state.commander_client
    cache = state.price_cache
    settings = state.settings

    return HealthResponse(
        status="ok",
        commander_host=settings.commander_host,
        connected=state.connection_healthy,
        session_authenticated=client.is_authenticated,
        session_age_seconds=(client.token_age_seconds if client.is_authenticated else None),
        last_price_fetch=cache.fetched_at,
        last_price_fetch_age_seconds=cache.age_seconds(),
        poll_interval_seconds=settings.poll_interval_seconds,
        last_error=client.last_error,
    )

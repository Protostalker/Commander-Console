"""
/api/mock router — mock mode controls (only active when mock.enabled: true).

These endpoints let you inspect and manipulate the mock state during
development/testing without real Commander hardware.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from models import FuelGrade, GradePriceUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mock", tags=["mock"])


def _require_mock(request: Request):
    if not request.app.state.mock_mode:
        raise HTTPException(
            status_code=403,
            detail="Mock endpoints are only available when mock.enabled is true in commander.yaml",
        )
    return request.app.state.mock_driver


@router.get("/state", summary="Inspect current mock Commander state")
async def get_mock_state(request: Request):
    """Return the current in-memory state of the mock Commander."""
    driver = _require_mock(request)
    return {
        "grades": [g.model_dump() for g in driver.get_grades()],
        "push_log": driver.push_log,
        "update_count": driver.update_count,
    }


@router.post("/reset", summary="Reset mock state to config defaults")
async def reset_mock(request: Request):
    """Reset the mock Commander back to the prices defined in commander.yaml."""
    driver = _require_mock(request)
    driver.reset()
    request.app.state.price_cache.invalidate()
    return {"status": "reset", "grades": [g.model_dump() for g in driver.get_grades()]}

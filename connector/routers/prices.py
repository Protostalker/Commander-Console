"""
/api/prices router — fuel price read, write, push, and history.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Request

from models import (
    FuelGrade,
    GradePriceUpdate,
    PriceHistoryRecord,
    PriceUpdateRequest,
    PricesResponse,
    PushResponse,
)
from naxml_builder import build_price_xml
from naxml_parser import parse_fuel_prices

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prices", tags=["prices"])

DB_PATH = "/app/data/history.db"


# ------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------

async def _init_db(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp            TEXT NOT NULL,
            grade_id             INTEGER NOT NULL,
            grade_name           TEXT NOT NULL,
            tier                 TEXT NOT NULL,
            old_price            REAL,
            new_price            REAL NOT NULL,
            pushed_to_dispensers INTEGER NOT NULL DEFAULT 0,
            triggered_by         TEXT NOT NULL DEFAULT 'api'
        )
        """
    )
    await db.commit()


async def _record_price_changes(
    db: aiosqlite.Connection,
    old_grades: list[FuelGrade],
    updates: list[GradePriceUpdate],
    pushed: bool,
    triggered_by: str = "api",
) -> None:
    old_map = {g.id: g for g in old_grades}
    now = datetime.now(timezone.utc).isoformat()

    for update in updates:
        old_grade = old_map.get(update.id)
        for tier, new_price in [("cash", update.cash), ("credit", update.credit)]:
            if new_price is None:
                continue
            # Use pending_prices as "old" since that's what we're updating
            old_price = None
            if old_grade:
                old_price = (old_grade.pending_prices or {}).get(tier)
            if old_price == new_price:
                continue
            await db.execute(
                """
                INSERT INTO price_history
                    (timestamp, grade_id, grade_name, tier, old_price, new_price,
                     pushed_to_dispensers, triggered_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now, update.id, update.name, tier, old_price, new_price,
                 1 if pushed else 0, triggered_by),
            )
    await db.commit()


async def _mark_pushed(db: aiosqlite.Connection, grade_ids: list[int]) -> None:
    for grade_id in grade_ids:
        await db.execute(
            """
            UPDATE price_history SET pushed_to_dispensers = 1
            WHERE grade_id = ?
              AND pushed_to_dispensers = 0
              AND id = (
                  SELECT id FROM price_history
                  WHERE grade_id = ? AND pushed_to_dispensers = 0
                  ORDER BY id DESC LIMIT 1
              )
            """,
            (grade_id, grade_id),
        )
    await db.commit()


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.get("", response_model=PricesResponse, summary="Get cached fuel prices")
async def get_prices(request: Request):
    """
    Return current fuel prices (In-Effect + Pending) for all active grades.
    Served from the in-memory cache refreshed on the poll interval.
    Use /api/prices/live to bypass the cache.
    """
    state = request.app.state

    async def fetch():
        if state.mock_mode:
            return state.mock_driver.get_grades()
        xml = await state.commander_client.get_fuel_prices()
        return parse_fuel_prices(xml)

    grades = await state.price_cache.get_or_fetch(fetch)
    return PricesResponse(
        grades=grades,
        from_cache=state.price_cache.is_fresh(),
        last_sync=state.price_cache.last_sync,
        mock_mode=state.mock_mode,
    )


@router.get("/live", response_model=PricesResponse, summary="Force-fetch prices from Commander")
async def get_prices_live(request: Request):
    """Bypass cache and fetch directly from Commander."""
    state = request.app.state

    async def fetch():
        if state.mock_mode:
            return state.mock_driver.get_grades()
        xml = await state.commander_client.get_fuel_prices()
        return parse_fuel_prices(xml)

    grades = await state.price_cache.get_or_fetch(fetch, force=True)
    return PricesResponse(
        grades=grades,
        from_cache=False,
        last_sync=state.price_cache.last_sync,
        mock_mode=state.mock_mode,
    )


@router.post("", response_model=PushResponse, summary="Update prices in Commander DB")
async def update_prices(request: Request, body: PriceUpdateRequest):
    """
    Write Pending price updates to the Commander database.

    Does NOT push to dispensers unless push_immediately=true.
    Call POST /api/prices/push to push separately.
    """
    state = request.app.state

    async def fetch():
        if state.mock_mode:
            return state.mock_driver.get_grades()
        xml = await state.commander_client.get_fuel_prices()
        return parse_fuel_prices(xml)

    old_grades = await state.price_cache.get_or_fetch(fetch)

    if state.mock_mode:
        state.mock_driver.apply_updates(body.grades)
        result_text = "mock:ok"
    else:
        # Build the fuel:fuelPrices XML payload for ufuelprices
        price_xml = build_price_xml(body.grades)
        result_text = await state.commander_client.update_prices(price_xml)

    state.price_cache.invalidate()

    pushed = False
    if body.push_immediately:
        if state.mock_mode:
            state.mock_driver.simulate_push()
        else:
            await state.commander_client.push_prices_to_dispensers()
        pushed = True
        logger.info("Prices updated and pushed to dispensers immediately")

    async with aiosqlite.connect(DB_PATH) as db:
        await _init_db(db)
        await _record_price_changes(db, old_grades, body.grades, pushed=pushed)

    return PushResponse(
        success=True,
        message="Prices updated in Commander DB"
                + (" and pushed to dispensers" if pushed else ""),
        raw_response=result_text if not state.mock_mode else None,
    )


@router.post("/push", response_model=PushResponse, summary="Push pending prices to dispensers")
async def push_prices(request: Request):
    """
    Commit Pending prices to In-Effect and push to physical dispensers.

    WARNING: This changes what customers pay at the pump.
    """
    state = request.app.state

    if state.mock_mode:
        state.mock_driver.simulate_push()
        result_text = "mock:push_ok"
    else:
        result_text = await state.commander_client.push_prices_to_dispensers()

    async with aiosqlite.connect(DB_PATH) as db:
        await _init_db(db)
        grade_ids = [g.id for g in (state.price_cache.grades or [])]
        if grade_ids:
            await _mark_pushed(db, grade_ids)

    logger.info("Prices pushed to dispensers (mock=%s)", state.mock_mode)
    return PushResponse(
        success=True,
        message="Prices pushed to dispensers",
        raw_response=result_text if not state.mock_mode else None,
    )


@router.post("/update-and-push", response_model=PushResponse,
             summary="Update DB then immediately push to dispensers")
async def update_and_push(request: Request, body: PriceUpdateRequest):
    """Atomic: write prices to Commander DB and push to dispensers in one call."""
    body.push_immediately = True
    return await update_prices(request, body)


@router.get("/history", response_model=list[PriceHistoryRecord],
            summary="Price change history log")
async def get_history(request: Request, limit: int = 100, offset: int = 0):
    """Return recent price change history from the local SQLite log, newest-first."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _init_db(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, timestamp, grade_id, grade_name, tier,
                   old_price, new_price, pushed_to_dispensers, triggered_by
            FROM price_history ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        PriceHistoryRecord(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            grade_id=row["grade_id"],
            grade_name=row["grade_name"],
            tier=row["tier"],
            old_price=row["old_price"],
            new_price=row["new_price"],
            pushed_to_dispensers=bool(row["pushed_to_dispensers"]),
            triggered_by=row["triggered_by"],
        )
        for row in rows
    ]

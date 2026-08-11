"""
commander-reader -- read-only FastAPI proxy for the Verifone Commander POS.

This service is READ ONLY. It only ever issues these NAXML commands:
validate (login), vfuelprices, vfueltotals, vmaintfprht, vfuelcfg. The
write commands ufuelprices and cfuelprices do not exist anywhere in this
codebase -- see app/commander_client.py.

Startup sequence:
  1. Load settings from env vars
  2. Login to Commander, pre-populate the price cache (non-fatal on failure)
  3. Start background tasks: price poll loop + session refresh loop
  4. Serve API requests

Graceful degradation: if Commander is unreachable at startup, the service
still starts (so /health, /docs work) and the poll loop keeps retrying.
Once Commander comes back, the cache updates automatically on the next poll.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import history
from .cache import PriceCache
from .commander_client import CommanderClient
from .config import load_settings
from .naxml_parser import parse_fuel_prices
from .routers import config as config_router
from .routers import health, metrics, prices, pumps, totals

logger = logging.getLogger(__name__)


async def _price_poll_loop(app: FastAPI) -> None:
    """Refresh the price cache from Commander on a fixed interval, forever."""
    state = app.state
    interval = state.settings.poll_interval_seconds
    logger.info("Price polling started -- interval: %ds", interval)

    while True:
        await asyncio.sleep(interval)
        try:
            xml = await state.commander_client.get_fuel_prices()
            grades = parse_fuel_prices(xml)
            old_grades = state.price_cache.grades
            await history.record_price_changes(state.settings.db_path, old_grades, grades)
            state.price_cache.set(grades)
            state.connection_healthy = True
            logger.debug("Price poll OK -- %d grades", len(grades))
        except Exception as e:
            state.connection_healthy = False
            logger.warning("Price poll failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app.state.settings = settings
    app.state.price_cache = PriceCache(ttl_seconds=settings.poll_interval_seconds)
    app.state.connection_healthy = False

    await history.init_db(settings.db_path)

    client = CommanderClient(
        host=settings.commander_host,
        port=settings.commander_port,
        username=settings.commander_username,
        password=settings.commander_password,
        verify_ssl=settings.commander_verify_ssl,
        session_refresh_minutes=settings.session_refresh_minutes,
    )
    app.state.commander_client = client

    logger.info(
        "commander-reader starting -- Commander at %s:%d (user: %s, READ-ONLY)",
        settings.commander_host, settings.commander_port, settings.commander_username,
    )

    background_tasks: list[asyncio.Task] = []

    try:
        ok = await client.login()
        app.state.connection_healthy = ok
        if ok:
            logger.info("Commander session established")
            xml = await client.get_fuel_prices()
            grades = parse_fuel_prices(xml)
            app.state.price_cache.set(grades)
            logger.info("Initial price fetch OK -- %d grades", len(grades))
        else:
            logger.warning(
                "Commander login failed at startup -- will keep retrying via the poll loop. Error: %s",
                client.last_error,
            )
    except Exception as e:
        app.state.connection_healthy = False
        logger.warning("Commander startup error: %s", e)

    background_tasks.append(asyncio.create_task(client.run_session_refresh()))
    background_tasks.append(asyncio.create_task(_price_poll_loop(app)))

    yield  # application runs here

    for task in background_tasks:
        task.cancel()
    for task in background_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass

    await client.close()
    logger.info("Commander HTTP client closed")


app = FastAPI(
    title="commander-reader",
    description=(
        "Read-only REST proxy for the Verifone Commander POS system. "
        "Exposes fuel prices, sales totals, pump totals, and site config as "
        "clean JSON over plain HTTP. No write commands are implemented "
        "anywhere in this service -- see app/commander_client.py."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(prices.router)
app.include_router(totals.router)
app.include_router(pumps.router)
app.include_router(config_router.router)
app.include_router(metrics.router)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "commander-reader",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }

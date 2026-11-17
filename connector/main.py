"""
commander-console — FastAPI application entry point.

REST API for reading and writing Verifone Commander fuel prices.
Runs on port 8100 (avoids conflicts with tls-decoded on 8000/5005).

Startup sequence:
  1. Load config from commander.yaml (+ env vars)
  2. If mock mode: initialize MockDriver
  3. If real mode: login to Commander, get session token, pre-populate cache
  4. Start background: price poll loop + daily session refresh
  5. Register API routers

Session token architecture:
  - Login once at startup (cmd=validate -> <cookie>TOKEN</cookie>)
  - Token stored in CommanderClient, passed in all subsequent requests
  - Daily refresh coroutine re-logins proactively (before token expires)
  - Auto-relogin on CGIPortal.LoginRequired fault
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import credentials_store
from cache import PriceCache
from commander_client import CommanderClient
from config import load_config
from mock_driver import MockDriver
from naxml_parser import parse_fuel_prices
from routers import credentials as credentials_router
from routers import mock, prices, status, totals

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background: price polling loop
# ---------------------------------------------------------------------------

async def _price_poll_loop(app: FastAPI) -> None:
    """
    Refresh the price cache from Commander on a fixed interval.
    Runs until cancelled by lifespan shutdown.
    """
    state = app.state
    interval = state.config.polling.price_poll_interval_seconds
    logger.info("Price polling started — interval: %ds", interval)

    while True:
        await asyncio.sleep(interval)
        try:
            if state.mock_mode:
                grades = state.mock_driver.get_grades()
            else:
                xml = await state.commander_client.get_fuel_prices()
                grades = parse_fuel_prices(xml)
            state.price_cache.set(grades)
            state.connection_healthy = True
            logger.debug("Price poll OK — %d grades", len(grades))
        except Exception as e:
            state.connection_healthy = False
            logger.warning("Price poll failed: %s", e)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    config = load_config()
    app.state.config = config
    app.state.mock_mode = config.mock.enabled
    # Guards POST /api/credentials only -- see routers/credentials.py.
    app.state.config_api_key = os.environ.get("CONFIG_API_KEY") or None

    app.state.price_cache = PriceCache(
        ttl_seconds=config.polling.price_poll_interval_seconds
    )

    background_tasks: list[asyncio.Task] = []

    if config.mock.enabled:
        # ---- MOCK MODE ----
        logger.info("Starting in MOCK MODE — %d grades configured", len(config.mock.grades))
        app.state.mock_driver = MockDriver(config.mock)
        app.state.commander_client = None
        app.state.connection_healthy = True
        app.state.price_cache.set(app.state.mock_driver.get_grades())

    else:
        # ---- REAL COMMANDER MODE ----
        logger.info(
            "Connecting to Commander at %s:%d (user: %s)",
            config.commander.host,
            config.commander.port,
            config.commander.username,
        )

        # Password can be set via env var for security
        username = config.commander.username
        password = os.environ.get("COMMANDER_PASSWORD") or config.commander.password
        if not password:
            logger.warning(
                "COMMANDER_PASSWORD not set! "
                "Set env var COMMANDER_PASSWORD or commander.yaml password field."
            )

        # A previously saved credential update (POST /api/credentials) wins
        # over commander.yaml/.env -- see credentials_store.py's docstring.
        saved = credentials_store.load()
        if saved:
            username, password = saved
            logger.info("Using saved Commander credentials override (user: %s)", username)

        client = CommanderClient(
            host=config.commander.host,
            port=config.commander.port,
            username=username,
            password=password,
            verify_ssl=config.commander.verify_ssl,
            timeout=config.commander.timeout_seconds,
            retry_attempts=config.commander.session_retry_attempts,
            lockout_threshold=config.commander.lockout_threshold,
        )
        app.state.commander_client = client
        app.state.mock_driver = None

        # Login and pre-populate cache (non-fatal on failure)
        try:
            ok = await client.login()
            app.state.connection_healthy = ok
            if ok:
                logger.info("Commander session established")
                xml = await client.get_fuel_prices()
                grades = parse_fuel_prices(xml)
                app.state.price_cache.set(grades)
                logger.info("Initial price fetch OK — %d grades", len(grades))
            else:
                logger.warning(
                    "Commander login failed at startup — will retry on first request. "
                    "Error: %s", client.last_error
                )
        except Exception as e:
            app.state.connection_healthy = False
            logger.warning("Commander startup error: %s", e)

        # Session refresh — re-logins every 25 min before the ~30 min token expiry.
        # Note: _ensure_token() also handles stale tokens per-request, so this
        # background task is just a latency optimization, not a correctness requirement.
        refresh_task = asyncio.create_task(client.run_session_refresh())
        background_tasks.append(refresh_task)
        logger.info("Session refresh task started (interval: %dm)", 25)

    # Background price polling
    poll_task = asyncio.create_task(_price_poll_loop(app))
    background_tasks.append(poll_task)

    yield  # Application runs here

    # Shutdown
    for task in background_tasks:
        task.cancel()
    for task in background_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass

    if app.state.commander_client:
        await app.state.commander_client.close()
        logger.info("Commander HTTP client closed")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="commander-console",
    description=(
        "Connector for the Verifone Commander POS system. "
        "Reads and writes fuel pricing data via the NAXML CGI API."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5010",
        "http://localhost:5173",   # Vite dev server
        "http://frontend",         # Docker service name
        "http://127.0.0.1:5010",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(status.router)
app.include_router(prices.router)
app.include_router(totals.router)
app.include_router(mock.router)
app.include_router(credentials_router.router)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "commander-console",
        "version": "0.2.0",
        "docs": "/docs",
        "status": "/api/status",
    }

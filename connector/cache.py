"""
In-memory price cache with TTL for commander-console.

Avoids hammering the Commander with every API request. Prices are fetched
from Commander on a configurable interval (default: 60s) and cached here.
Individual requests can bypass the cache with force_refresh=True.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Callable, Coroutine, Optional

from models import FuelGrade

logger = logging.getLogger(__name__)


class PriceCache:
    """
    Thread-safe in-memory cache for fuel grade prices.

    Attributes:
        ttl_seconds: How long a cached result is considered fresh.
        grades: The cached list of FuelGrade objects (None if not yet populated).
        last_sync: UTC datetime of the last successful fetch.
        _lock: asyncio lock preventing concurrent cache refreshes.
    """

    def __init__(self, ttl_seconds: int = 60) -> None:
        self.ttl_seconds = ttl_seconds
        self.grades: Optional[list[FuelGrade]] = None
        self.last_sync: Optional[datetime] = None
        self._fetched_at: Optional[float] = None   # monotonic clock time
        self._lock = asyncio.Lock()

    def is_fresh(self) -> bool:
        """Return True if cached data exists and is within the TTL."""
        if self.grades is None or self._fetched_at is None:
            return False
        return (time.monotonic() - self._fetched_at) < self.ttl_seconds

    def set(self, grades: list[FuelGrade]) -> None:
        """Store a fresh set of grades and record the sync time."""
        self.grades = grades
        self._fetched_at = time.monotonic()
        self.last_sync = datetime.now(timezone.utc)
        logger.debug("Price cache updated: %d grades", len(grades))

    def invalidate(self) -> None:
        """Force the next read to re-fetch from Commander."""
        self._fetched_at = None
        logger.debug("Price cache invalidated")

    def last_sync_age_seconds(self) -> Optional[float]:
        """Seconds since last sync, or None if never synced."""
        if self._fetched_at is None:
            return None
        return time.monotonic() - self._fetched_at

    async def get_or_fetch(
        self,
        fetch_fn: Callable[[], Coroutine[None, None, list[FuelGrade]]],
        force: bool = False,
    ) -> list[FuelGrade]:
        """
        Return cached grades if fresh, otherwise call fetch_fn to refresh.

        Args:
            fetch_fn: Async callable that fetches fresh grades from Commander.
            force: If True, bypass the TTL and always call fetch_fn.

        Returns:
            Current list of FuelGrade objects.

        Raises:
            Whatever fetch_fn raises on failure.
        """
        if not force and self.is_fresh() and self.grades is not None:
            return self.grades

        async with self._lock:
            # Re-check inside lock (another coroutine may have refreshed while we waited)
            if not force and self.is_fresh() and self.grades is not None:
                return self.grades

            logger.info("Fetching prices from Commander (force=%s)", force)
            fresh = await fetch_fn()
            self.set(fresh)
            return fresh

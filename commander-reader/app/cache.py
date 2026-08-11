"""
In-memory TTL cache for the current fuel price snapshot.

Avoids hammering the Commander with every /prices request. The background
poll loop in main.py refreshes this on POLL_INTERVAL_SECONDS; /prices/live
also updates it via a direct fetch.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from .models import FuelGrade


class PriceCache:
    def __init__(self, ttl_seconds: int = 60) -> None:
        self.ttl_seconds = ttl_seconds
        self.grades: Optional[list[FuelGrade]] = None
        self.fetched_at: Optional[datetime] = None
        self._fetched_monotonic: Optional[float] = None

    def is_fresh(self) -> bool:
        if self.grades is None or self._fetched_monotonic is None:
            return False
        return (time.monotonic() - self._fetched_monotonic) < self.ttl_seconds

    def age_seconds(self) -> Optional[float]:
        if self._fetched_monotonic is None:
            return None
        return time.monotonic() - self._fetched_monotonic

    def set(self, grades: list[FuelGrade]) -> None:
        self.grades = grades
        self._fetched_monotonic = time.monotonic()
        self.fetched_at = datetime.now(timezone.utc)

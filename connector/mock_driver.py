"""
Mock driver for commander-console.

Stands in for the real Commander unit when mock.enabled=true.
Mirrors the Commander's two-tier pricing model:
  - prices        — In-Effect (what dispensers currently charge)
  - pending_prices — Pending (staged, pushed via simulate_push)
"""

from __future__ import annotations

import asyncio
import copy
import logging
from datetime import datetime, timezone
from typing import Any

from config import MockConfig, MockGrade
from models import FuelGrade, GradePriceUpdate

logger = logging.getLogger(__name__)

MOCK_DELAY_SECONDS = 0.3


class MockDriver:
    """In-memory simulation of a Verifone Commander's fuel price state."""

    def __init__(self, mock_config: MockConfig) -> None:
        self._config = mock_config
        self._grades: list[FuelGrade] = self._build_grades(mock_config.grades)
        self.push_log: list[dict[str, Any]] = []
        self.update_count: int = 0

    def get_grades(self) -> list[FuelGrade]:
        """Return current grades (both In-Effect and Pending tiers)."""
        return copy.deepcopy(self._grades)

    def apply_updates(self, updates: list[GradePriceUpdate]) -> None:
        """
        Apply price updates to the Pending tier (simulates ufuelprices).
        Does NOT change In-Effect prices.
        """
        grade_map = {g.id: g for g in self._grades}
        for update in updates:
            if update.id not in grade_map:
                logger.warning("Mock: unknown grade ID %d, skipping", update.id)
                continue
            grade = grade_map[update.id]
            if not grade.pending_prices:
                grade.pending_prices = dict(grade.prices)
            if update.cash is not None:
                grade.pending_prices["cash"] = update.cash
            if update.credit is not None:
                grade.pending_prices["credit"] = update.credit
        self.update_count += 1
        logger.info("Mock: applied %d updates to Pending tier", len(updates))

    def simulate_push(self) -> None:
        """
        Simulate cfuelprices: promote Pending -> In-Effect.
        """
        changes = []
        for grade in self._grades:
            if not grade.pending_prices:
                continue
            for mop in ("cash", "credit"):
                old = grade.prices.get(mop)
                new = grade.pending_prices.get(mop)
                if new is not None and old != new:
                    changes.append((grade.name, mop, old, new))
                    grade.prices[mop] = new

        if changes:
            logger.info("Mock: pushed %d price changes to In-Effect", len(changes))
            for name, mop, old, new in changes:
                logger.info("  %s %s: $%.3f -> $%.3f", name, mop, old or 0, new)
        else:
            logger.info("Mock: push completed — no changes")

        self.push_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "changes": [
                {"grade": n, "mop": m, "old": o, "new": v}
                for n, m, o, v in changes
            ],
        })

    def reset(self) -> None:
        """Reset to original config defaults."""
        self._grades = self._build_grades(self._config.grades)
        self.push_log.clear()
        self.update_count = 0
        logger.info("Mock: state reset to config defaults")

    @staticmethod
    def _build_grades(grade_configs: list[MockGrade]) -> list[FuelGrade]:
        return [
            FuelGrade(
                id=g.id,
                name=g.name,
                prices={"cash": g.cash_price, "credit": g.credit_price},
                pending_prices={"cash": g.cash_price, "credit": g.credit_price},
            )
            for g in grade_configs
        ]

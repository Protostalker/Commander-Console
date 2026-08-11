"""
SQLite-backed price change history.

The poll loop (and /prices/live) calls record_price_changes() after each
fetch, diffing the freshly parsed grades against the previous cached
snapshot. Any change to in_effect.cash / in_effect.credit / pending.cash /
pending.credit is logged as a row. This is purely local bookkeeping --
detection only, no Commander writes involved anywhere in this module.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import aiosqlite

from .models import FuelGrade, PriceHistoryRecord

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS price_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT NOT NULL,
    grade_id     INTEGER NOT NULL,
    grade_name   TEXT NOT NULL,
    tier         TEXT NOT NULL,
    old_price    REAL,
    new_price    REAL NOT NULL,
    detected_by  TEXT NOT NULL DEFAULT 'poll'
)
"""


async def init_db(db_path: str) -> None:
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_CREATE_TABLE_SQL)
        await db.commit()


def _tier_pairs(grade: FuelGrade) -> list[tuple[str, float | None]]:
    return [
        ("in_effect_cash", grade.in_effect.cash),
        ("in_effect_credit", grade.in_effect.credit),
        ("pending_cash", grade.pending.cash),
        ("pending_credit", grade.pending.credit),
    ]


async def record_price_changes(
    db_path: str,
    old_grades: list[FuelGrade] | None,
    new_grades: list[FuelGrade],
    detected_by: str = "poll",
) -> int:
    """Diff old vs new grades and append any changes. Returns rows written."""
    if not old_grades:
        return 0  # nothing to diff against on the very first fetch

    old_map = {g.id: g for g in old_grades}
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    for grade in new_grades:
        old_grade = old_map.get(grade.id)
        old_pairs = dict(_tier_pairs(old_grade)) if old_grade else {}
        for tier, new_price in _tier_pairs(grade):
            if new_price is None:
                continue
            old_price = old_pairs.get(tier)
            if old_price == new_price:
                continue
            rows.append((now, grade.id, grade.name, tier, old_price, new_price, detected_by))

    if not rows:
        return 0

    async with aiosqlite.connect(db_path) as db:
        await db.execute(_CREATE_TABLE_SQL)
        await db.executemany(
            """
            INSERT INTO price_history
                (timestamp, grade_id, grade_name, tier, old_price, new_price, detected_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        await db.commit()

    logger.info("Recorded %d price change(s)", len(rows))
    return len(rows)


async def get_history(db_path: str, limit: int = 100, offset: int = 0) -> list[PriceHistoryRecord]:
    await init_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, timestamp, grade_id, grade_name, tier, old_price, new_price, detected_by
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
            detected_by=row["detected_by"],
        )
        for row in rows
    ]

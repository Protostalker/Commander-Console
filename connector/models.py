"""
Pydantic models for commander-console.

Core data structures:
  FuelGrade         — one fuel product with in-effect and pending prices
  GradePriceUpdate  — a price change request for one grade
  PriceUpdateRequest — API request body for POST /api/prices
  PriceHistoryRecord — one entry in the SQLite change log
  StatusResponse    — GET /api/status response
  PushResponse      — POST /api/push response
  PricesResponse    — GET /api/prices response

Price model
-----------
The Commander stores up to two price tiers per product:
  Tier 1 (In Effect) — what dispensers currently charge
  Tier 2 (Pending)   — staged prices, committed via cfuelprices

Each tier has cash and credit prices (simplified from the raw
3 service-levels x 2 MOPs structure; we use SELF/svc-level-1 as canonical).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FuelGrade(BaseModel):
    """A fuel grade (Regular, Plus, Diesel, …) with In-Effect and Pending prices."""

    id: int = Field(..., description="Commander grade sysid (1-20)")
    name: str = Field(..., description="Grade name as stored on Commander")

    # Tier 1 — In Effect (what dispensers currently charge)
    prices: dict[str, float | None] = Field(
        default_factory=dict,
        description="In-Effect prices: {'cash': 5.579, 'credit': 5.579}",
    )

    # Tier 2 — Pending (staged, not yet pushed to dispensers)
    pending_prices: dict[str, float | None] = Field(
        default_factory=dict,
        description="Pending prices: {'cash': 4.999, 'credit': 5.099}",
    )

    # Convenience accessors
    @property
    def cash_price(self) -> float | None:
        return self.prices.get("cash")

    @property
    def credit_price(self) -> float | None:
        return self.prices.get("credit")

    @property
    def pending_cash_price(self) -> float | None:
        return self.pending_prices.get("cash")

    @property
    def pending_credit_price(self) -> float | None:
        return self.pending_prices.get("credit")


class GradePriceUpdate(BaseModel):
    """Payload for updating prices on a single grade."""

    id: int = Field(..., description="Commander grade sysid")
    name: str = Field(..., description="Grade name")
    cash: float | None = Field(None, ge=0, description="New cash price (omit to leave unchanged)")
    credit: float | None = Field(None, ge=0, description="New credit price (omit to leave unchanged)")


class PriceUpdateRequest(BaseModel):
    """Request body for POST /api/prices."""

    grades: list[GradePriceUpdate] = Field(..., description="Grade price updates")
    push_immediately: bool = Field(
        False,
        description="If true, also push to dispensers after writing to Commander DB",
    )


class PriceHistoryRecord(BaseModel):
    """One entry in the price change log."""

    id: int | None = None
    timestamp: datetime
    grade_id: int
    grade_name: str
    tier: str                   # 'cash' or 'credit'
    old_price: float | None
    new_price: float
    pushed_to_dispensers: bool
    triggered_by: str = "api"   # 'api', 'mock', etc.


class StatusResponse(BaseModel):
    """Response for GET /api/status."""

    connected: bool
    mock_mode: bool
    commander_host: str
    last_sync: datetime | None = None
    last_sync_age_seconds: float | None = None
    session_token_age_seconds: float | None = None
    session_authenticated: bool = False
    error: str | None = None
    # Circuit breaker -- see commander_client.py. locked_out=true means the
    # poll loop has stopped attempting Commander logins entirely; fix via
    # POST /api/credentials, which also clears this.
    consecutive_login_failures: int = 0
    locked_out: bool = False


class CredentialsUpdateRequest(BaseModel):
    """POST /api/credentials -- rotate the Commander login this service
    uses, live, no restart. Password is required every time (never echoed
    back); username is optional -- omit to keep the current one."""

    username: str | None = None
    password: str = Field(..., min_length=1)


class CredentialsUpdateResponse(BaseModel):
    ok: bool
    username: str
    error: str | None = Field(
        None, description="Set if the validating login with the new credentials failed"
    )


class PushResponse(BaseModel):
    """Response after pushing prices to dispensers."""

    success: bool
    message: str
    raw_response: str | None = None


class PricesResponse(BaseModel):
    """Response for GET /api/prices."""

    grades: list[FuelGrade]
    from_cache: bool
    last_sync: datetime | None = None
    mock_mode: bool


# ---------------------------------------------------------------------------
# Fuel totals (vfueltotals)
# ---------------------------------------------------------------------------

class FuelGradeTotals(BaseModel):
    """Aggregated sales totals for one fuel grade across all dispensers."""

    name: str = Field(..., description="Grade name (e.g. REGULAR, DIESEL#2)")
    volume_gallons: float = Field(..., description="Total gallons dispensed")
    revenue_usd: float = Field(..., description="Total revenue in USD")
    avg_price_per_gallon: float | None = Field(
        None, description="Implied average price (revenue / volume)"
    )


class FuelTotals(BaseModel):
    """Sales totals for one period (shift / day / month / year)."""

    period_type: str = Field(..., description="'shift', 'day', 'month', or 'year'")
    period_label: str = Field(..., description="Human-readable period label from Commander")
    period_begin: str | None = Field(None, description="ISO-8601 period begin timestamp")
    period_seq_num: int | None = Field(None, description="Commander period sequence number")
    site_id: int | None = Field(None, description="Site ID")
    grades: list[FuelGradeTotals] = Field(default_factory=list)
    total_volume_gallons: float = Field(0.0, description="Sum across all grades")
    total_revenue_usd: float = Field(0.0, description="Sum across all grades")


class TotalsResponse(BaseModel):
    """Response for GET /api/totals."""

    period: str
    totals: FuelTotals
    mock_mode: bool

"""
Pydantic response models for commander-reader.

Every model here represents a READ-ONLY view of Commander data. There are
no request/write models in this file on purpose -- this service never
constructs a NAXML write payload.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

class PriceTier(BaseModel):
    cash: float | None = None
    credit: float | None = None


class FuelGrade(BaseModel):
    """One fuel grade with In-Effect (live) and Pending (staged) prices."""

    id: int = Field(..., description="Commander grade sysid")
    name: str = Field(..., description="Grade name as stored on Commander")
    in_effect: PriceTier = Field(default_factory=PriceTier, description="What dispensers currently charge")
    pending: PriceTier = Field(default_factory=PriceTier, description="Staged prices, not yet in effect")


class PricesResponse(BaseModel):
    grades: list[FuelGrade]
    from_cache: bool
    fetched_at: datetime | None = Field(None, description="UTC timestamp of the underlying fetch")
    cache_age_seconds: float | None = None
    stale: bool = Field(False, description="True if the cached data is older than the poll interval")


class PriceHistoryRecord(BaseModel):
    """One detected price change, logged locally. Detection only -- no writes."""

    id: int | None = None
    timestamp: datetime
    grade_id: int
    grade_name: str
    tier: str = Field(..., description="'in_effect_cash', 'in_effect_credit', 'pending_cash', or 'pending_credit'")
    old_price: float | None
    new_price: float
    detected_by: str = "poll"


# ---------------------------------------------------------------------------
# Totals (vfueltotals)
# ---------------------------------------------------------------------------

class FuelGradeTotals(BaseModel):
    name: str = Field(..., description="Grade name (e.g. REGULAR, DIESEL#2)")
    volume_gallons: float
    revenue_usd: float
    avg_price_per_gallon: float | None = None


class TotalsResponse(BaseModel):
    period: str = Field(..., description="'shift', 'day', 'month', or 'year'")
    period_begin: str | None = None
    period_seq_num: int | None = None
    grades: list[FuelGradeTotals] = Field(default_factory=list)
    total_volume_gallons: float = 0.0
    total_revenue_usd: float = 0.0


# ---------------------------------------------------------------------------
# Pumps (vmaintfprht) -- lifetime mechanical totals
# ---------------------------------------------------------------------------

class HoseTotals(BaseModel):
    id: int
    product_name: str
    total_volume_gallons: float
    total_revenue_usd: float
    total_transactions: int | None = None


class PumpTotals(BaseModel):
    id: int
    hoses: list[HoseTotals] = Field(default_factory=list)


class PumpsResponse(BaseModel):
    pumps: list[PumpTotals] = Field(default_factory=list)
    site_total_volume_gallons: float = 0.0
    site_total_revenue_usd: float = 0.0
    site_total_transactions: int | None = None


# ---------------------------------------------------------------------------
# Config (vfuelcfg) -- returned as raw XML for now, per spec
# ---------------------------------------------------------------------------

class ConfigResponse(BaseModel):
    site_id: int | None = None
    raw_xml: str


class CredentialsUpdateRequest(BaseModel):
    """POST /config/credentials -- rotate the Commander login this service
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


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    commander_host: str
    connected: bool
    session_authenticated: bool
    session_age_seconds: float | None = None
    last_price_fetch: datetime | None = None
    last_price_fetch_age_seconds: float | None = None
    poll_interval_seconds: int
    last_error: str | None = None
    # Circuit breaker -- see commander_client.py. locked_out=true means the
    # poll loop has stopped attempting Commander logins entirely; fix via
    # POST /config/credentials, which also clears this.
    consecutive_login_failures: int = 0
    locked_out: bool = False

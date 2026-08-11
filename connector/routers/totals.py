"""
/api/totals router — fuel sales totals by period (shift/day/month/year).

Commander command: vfueltotals
  Returns aggregated volume + revenue per grade, per dispenser.
  We aggregate across all dispensers to get station-wide totals.

Period parameter:
  1 = Shift (current daypart, ~8h)
  2 = Day   (today, default)
  3 = Month (calendar month)
  4 = Year  (calendar year)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from models import FuelGradeTotals, FuelTotals, TotalsResponse
from naxml_parser import parse_fuel_totals

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/totals", tags=["totals"])

# Period number → human name
PERIOD_MAP = {
    1: "shift",
    2: "day",
    3: "month",
    4: "year",
}

# Mock data: plausible looking totals per grade
_MOCK_GRADES: list[dict] = [
    {"name": "REGULAR",  "volume": 1850.5,  "money": 7945.65},
    {"name": "PLUS",     "volume": 420.2,   "money": 1848.28},
    {"name": "SUPER",    "volume": 310.8,   "money": 1422.96},
    {"name": "DIESEL#2", "volume": 2740.0,  "money": 11673.38},
]


def _mock_totals(period: int) -> FuelTotals:
    """Return plausible mock totals (multiplied up for longer periods)."""
    mult = {1: 0.33, 2: 1.0, 3: 28.0, 4: 365.0}.get(period, 1.0)
    period_label = PERIOD_MAP.get(period, "day").title()
    grades = []
    total_vol = 0.0
    total_rev = 0.0
    for g in _MOCK_GRADES:
        vol = round(g["volume"] * mult, 3)
        mon = round(g["money"] * mult, 2)
        avg = round(mon / vol, 4) if vol > 0 else None
        grades.append(FuelGradeTotals(
            name=g["name"],
            volume_gallons=vol,
            revenue_usd=mon,
            avg_price_per_gallon=avg,
        ))
        total_vol += vol
        total_rev += mon
    return FuelTotals(
        period_type=PERIOD_MAP.get(period, "day"),
        period_label=period_label,
        period_begin=None,
        period_seq_num=None,
        site_id=1,
        grades=grades,
        total_volume_gallons=round(total_vol, 3),
        total_revenue_usd=round(total_rev, 2),
    )


@router.get(
    "",
    response_model=TotalsResponse,
    summary="Fuel sales totals by period",
)
async def get_totals(
    request: Request,
    period: int = Query(
        default=2,
        ge=1,
        le=4,
        description="Period: 1=Shift, 2=Day, 3=Month, 4=Year",
    ),
):
    """
    Return aggregated fuel sales totals (volume + revenue) by grade.

    Data comes from the Commander's running counters, aggregated
    across all dispensers. Totals are cumulative within the selected
    period window (e.g. Day = since the current day started at the POS).
    """
    state = request.app.state
    period_name = PERIOD_MAP.get(period, "day")

    if state.mock_mode:
        totals = _mock_totals(period)
        return TotalsResponse(period=period_name, totals=totals, mock_mode=True)

    try:
        xml = await state.commander_client.get_fuel_totals(period=period)
        totals = parse_fuel_totals(xml)
    except Exception as e:
        logger.error("vfueltotals (period=%d) failed: %s", period, e)
        raise HTTPException(status_code=502, detail=f"Commander error: {e}") from e

    return TotalsResponse(period=period_name, totals=totals, mock_mode=False)

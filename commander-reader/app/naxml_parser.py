"""
NAXML XML -> Python parsers for commander-reader.

Forked from commander-console/connector/naxml_parser.py. parse_fuel_prices
and parse_fuel_totals are ports of code already proven against a live
Commander unit (just reshaped to this project's models). parse_pump_totals
is NEW and UNVERIFIED -- see the warning in its docstring.

Response formats handled:

1. Login (domain:credential) -- token extraction lives in commander_client.py.

2. Fuel prices (fuel:fuelPrices):
   <fuel:fuelPrices ...>
     <fuelProducts maxSize="20">
       <fuelProduct sysid="1" name="REGULAR" NAXMLFuelGradeID="1">
         <prices>
           <!-- tier: 1=In Effect, 2=Pending. servLevel: 1=SELF. mop: 1=CASH, 2=CREDIT -->
           <price tier="1" servLevel="1" mop="1">5.579</price>
           ...
         </prices>
       </fuelProduct>
     </fuelProducts>
   </fuel:fuelPrices>

3. Fuel totals (fuel:fuelTotals) -- one <fpDispenserData> per dispenser x grade:
   <fuel:fuelTotals ...>
     <vs:period sysid="2" periodType="day" name="Day" periodSeqNum="506"
                periodBeginDate="2026-08-09T20:00:06-07:00"/>
     <vs:site>1</vs:site>
     <fpDispenserData>
       <fuelingPositionId>1</fuelingPositionId>
       <productNumber name="DIESEL#2">7</productNumber>
       <fuelVolume uom="G">22747.860</fuelVolume>
       <fuelMoney currency="USD">152727.75</fuelMoney>
       <productID>7</productID>
     </fpDispenserData>
     ...
   </fuel:fuelTotals>

4. Fault:
   <VFI:Response xmlns:VFI="urn:vfi-sapphire:np.domain.2001-07-01">
     <VFI:Fault>
       <faultCode>CGIPortal.LoginRequired</faultCode>
       <faultString>Session has expired</faultString>
     </VFI:Fault>
   </VFI:Response>
"""

from __future__ import annotations

import logging
from typing import Optional
from xml.etree import ElementTree as ET

from .models import (
    FuelGrade,
    FuelGradeTotals,
    HoseTotals,
    PriceTier,
    PumpsResponse,
    PumpTotals,
    TotalsResponse,
)

logger = logging.getLogger(__name__)

NS = {
    "fuel": "urn:vfi-sapphire:fuel.2001-10-01",
    "vs": "urn:vfi-sapphire:vs.2001-10-01",
    "domain": "urn:vfi-sapphire:np.domain.2001-07-01",
    "VFI": "urn:vfi-sapphire:np.domain.2001-07-01",
    "fuelcfg": "urn:vfi-sapphire:fuelcfg.2001-10-01",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_fuel_prices(xml_str: str) -> list[FuelGrade]:
    """
    Parse a vfuelprices response into a list of FuelGrade objects, one per
    active product slot (name != "UNUSED"). Raises ValueError on failure.
    """
    root = _parse_root(xml_str)
    grades = _parse_fuel_prices_root(root)
    if not grades:
        logger.warning("No fuel grades found. Root tag: %s. XML: %s", root.tag, xml_str[:500])
        raise ValueError(f"No fuel grades found in response (root: <{root.tag}>)")
    logger.debug("Parsed %d fuel grades", len(grades))
    return grades


def parse_fuel_totals(xml_str: str, period_name: str = "") -> TotalsResponse:
    """
    Parse a vfueltotals response into a TotalsResponse. Aggregates volume
    and revenue by grade name across all dispensers. Raises ValueError on
    failure.
    """
    root = _parse_root(xml_str)

    period_el = _find_any(root, "period")
    period_type = period_name
    period_begin = None
    period_seq_num = None

    if period_el is not None:
        period_type = period_el.get("periodType", period_name).lower() or period_name
        period_begin = period_el.get("periodBeginDate")
        period_seq_num = _safe_int(period_el.get("periodSeqNum"))

    grade_totals: dict[str, dict] = {}

    for fp_el in root.iter():
        if _local_name(fp_el.tag) != "fpDispenserData":
            continue

        prod_el = vol_el = mon_el = None
        for child in fp_el:
            local = _local_name(child.tag)
            if local == "productNumber":
                prod_el = child
            elif local == "fuelVolume":
                vol_el = child
            elif local == "fuelMoney":
                mon_el = child

        if prod_el is None:
            continue
        grade_name = (prod_el.get("name") or "").strip()
        if not grade_name:
            continue

        volume = _safe_float(vol_el.text if vol_el is not None else None) or 0.0
        money = _safe_float(mon_el.text if mon_el is not None else None) or 0.0

        bucket = grade_totals.setdefault(grade_name, {"volume": 0.0, "money": 0.0})
        bucket["volume"] += volume
        bucket["money"] += money

    grades: list[FuelGradeTotals] = []
    total_volume = 0.0
    total_revenue = 0.0

    for name, data in sorted(grade_totals.items()):
        vol = data["volume"]
        mon = data["money"]
        avg = (mon / vol) if vol > 0 else None
        grades.append(FuelGradeTotals(
            name=name,
            volume_gallons=round(vol, 3),
            revenue_usd=round(mon, 2),
            avg_price_per_gallon=round(avg, 4) if avg is not None else None,
        ))
        total_volume += vol
        total_revenue += mon

    return TotalsResponse(
        period=period_type or period_name or "day",
        period_begin=period_begin,
        period_seq_num=period_seq_num,
        grades=grades,
        total_volume_gallons=round(total_volume, 3),
        total_revenue_usd=round(total_revenue, 2),
    )


def parse_pump_totals(xml_str: str) -> PumpsResponse:
    """
    Parse a vmaintfprht response into a PumpsResponse.

    *** UNVERIFIED AGAINST LIVE HARDWARE ***
    vmaintfprht was never called against the real Commander unit while this
    project was built (only vfuelprices and vfueltotals were confirmed
    live). This parser is a best-effort port of the vfueltotals pattern --
    it walks the tree for per-pump/per-hose records and tries several
    plausible tag/attribute names for pump id, hose id, product name,
    volume, revenue, and transaction count. It is defensive (skips records
    it can't understand rather than crashing) but the field names below are
    an educated guess, not a confirmed schema.

    ACTION ITEM before relying on GET /pumps in production: hit this
    endpoint once against the real Commander, compare the raw XML (log it
    at DEBUG) against the tag names guessed here, and adjust as needed.
    """
    root = _parse_root(xml_str)

    site_el = _find_any(root, "site")
    _ = _safe_int(site_el.text) if site_el is not None else None  # site id, currently unused in response shape

    # Candidate record wrapper tags, in order of likelihood.
    record_tags = {"fpDispenserData", "fpHoseData", "hoseData", "maintFpData", "fuelHoseTotals"}

    pump_map: dict[int, dict[int, HoseTotals]] = {}

    for el in root.iter():
        local = _local_name(el.tag)
        if local not in record_tags:
            continue

        fields = {_local_name(child.tag): child for child in el}

        pump_id = _first_int(fields, "fuelingPositionId", "pumpId", "deviceId", "fpId")
        hose_id = _first_int(fields, "hoseId", "nozzleId", "hosePosition", "position")
        if hose_id is None:
            hose_id = 1  # single-hose pumps / unknown hose numbering

        product_el = fields.get("productNumber") or fields.get("productName") or fields.get("product")
        product_name = (product_el.get("name") if product_el is not None and product_el.get("name") else
                         (product_el.text if product_el is not None else None))
        product_name = (product_name or "UNKNOWN").strip()

        volume = _first_float(fields, "fuelVolume", "totalVolume", "volume")
        money = _first_float(fields, "fuelMoney", "totalMoney", "revenue", "totalRevenue")
        txn_count = _first_int(fields, "numberOfSales", "transactionCount", "saleCount", "totalTransactions")

        if pump_id is None or (volume is None and money is None):
            continue  # not a record shape we recognize -- skip rather than guess wrong

        hose = HoseTotals(
            id=hose_id,
            product_name=product_name,
            total_volume_gallons=round(volume or 0.0, 3),
            total_revenue_usd=round(money or 0.0, 2),
            total_transactions=txn_count,
        )
        pump_map.setdefault(pump_id, {})[hose_id] = hose

    if not pump_map:
        logger.warning(
            "parse_pump_totals: no recognizable pump records in vmaintfprht response. "
            "Schema likely differs from the guessed tag names -- inspect raw XML. First 800 chars: %s",
            xml_str[:800],
        )
        raise ValueError(
            "Could not parse any pump records from vmaintfprht response -- "
            "the schema differs from what parse_pump_totals() expects. See server logs "
            "for the raw XML and update app/naxml_parser.py::parse_pump_totals accordingly."
        )

    pumps = [
        PumpTotals(id=pump_id, hoses=sorted(hoses.values(), key=lambda h: h.id))
        for pump_id, hoses in sorted(pump_map.items())
    ]

    site_total_volume = sum(h.total_volume_gallons for p in pumps for h in p.hoses)
    site_total_revenue = sum(h.total_revenue_usd for p in pumps for h in p.hoses)
    txn_values = [h.total_transactions for p in pumps for h in p.hoses if h.total_transactions is not None]
    site_total_transactions = sum(txn_values) if txn_values else None

    return PumpsResponse(
        pumps=pumps,
        site_total_volume_gallons=round(site_total_volume, 3),
        site_total_revenue_usd=round(site_total_revenue, 2),
        site_total_transactions=site_total_transactions,
    )


def extract_site_id(xml_str: str) -> Optional[int]:
    """Best-effort extraction of <vs:site> from any Commander response."""
    try:
        root = _parse_root(xml_str)
    except ValueError:
        return None
    site_el = _find_any(root, "site")
    if site_el is None or site_el.text is None:
        return None
    return _safe_int(site_el.text)


# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------

def _parse_root(xml_str: str) -> ET.Element:
    xml_str = xml_str.strip()
    if not xml_str:
        raise ValueError("Empty XML response from Commander")
    if "<faultCode>" in xml_str:
        fault = _extract_simple(xml_str, "faultCode")
        raise ValueError(f"Commander returned fault: {fault}")
    try:
        return ET.fromstring(xml_str)
    except ET.ParseError as e:
        raise ValueError(f"XML parse error: {e}. Raw (first 500): {xml_str[:500]}") from e


def _parse_fuel_prices_root(root: ET.Element) -> list[FuelGrade]:
    products_el = _find_any(root, "fuelProducts")
    if products_el is None:
        products_el = root if root.tag.endswith("fuelProducts") else None
    if products_el is None:
        return []

    grades: list[FuelGrade] = []

    for product_el in products_el:
        if _local_name(product_el.tag) != "fuelProduct":
            continue

        sysid = product_el.get("sysid")
        name = (product_el.get("name") or "").strip()
        if not sysid or not name or name.upper() == "UNUSED":
            continue

        grade_id = _safe_int(sysid)
        if grade_id is None:
            continue

        prices_el = product_el.find("prices")
        if prices_el is None:
            continue

        in_effect_cash = in_effect_credit = pending_cash = pending_credit = None

        for price_el in prices_el:
            if _local_name(price_el.tag) != "price":
                continue
            tier = _safe_int(price_el.get("tier"))
            serv_level = _safe_int(price_el.get("servLevel"))
            mop = _safe_int(price_el.get("mop"))
            value = _safe_float(price_el.text)
            if None in (tier, serv_level, mop, value):
                continue

            # SELF (servLevel=1) prices are used as canonical -- most sites
            # have equal prices across service levels.
            if serv_level == 1:
                if tier == 1 and mop == 1:
                    in_effect_cash = value
                elif tier == 1 and mop == 2:
                    in_effect_credit = value
                elif tier == 2 and mop == 1:
                    pending_cash = value
                elif tier == 2 and mop == 2:
                    pending_credit = value

        grades.append(FuelGrade(
            id=grade_id,
            name=name,
            in_effect=PriceTier(cash=in_effect_cash, credit=in_effect_credit),
            pending=PriceTier(cash=pending_cash, credit=pending_credit),
        ))

    grades.sort(key=lambda g: g.id)
    return grades


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _find_any(root: ET.Element, local_name: str) -> Optional[ET.Element]:
    for prefix, ns in NS.items():
        el = root.find(f".//{{{ns}}}{local_name}")
        if el is not None:
            return el
    for el in root.iter():
        if _local_name(el.tag) == local_name:
            return el
    return None


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _extract_simple(xml_text: str, tag: str) -> Optional[str]:
    open_tag = f"<{tag}>"
    close_tag = f"</{tag}>"
    start = xml_text.find(open_tag)
    if start == -1:
        return None
    end = xml_text.find(close_tag, start)
    if end == -1:
        return None
    return xml_text[start + len(open_tag):end].strip()


def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _first_int(fields: dict[str, ET.Element], *candidates: str) -> Optional[int]:
    for name in candidates:
        el = fields.get(name)
        if el is not None:
            val = _safe_int(el.text) if el.text else _safe_int(el.get("sysid"))
            if val is not None:
                return val
    return None


def _first_float(fields: dict[str, ET.Element], *candidates: str) -> Optional[float]:
    for name in candidates:
        el = fields.get(name)
        if el is not None and el.text:
            val = _safe_float(el.text)
            if val is not None:
                return val
    return None

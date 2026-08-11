"""
NAXML parser for Verifone Commander responses.

Handles the two main response formats discovered on the live Commander unit:

1. Login response (domain:credential):
   <domain:credential xmlns:domain="urn:vfi-sapphire:np.domain.2001-07-01"
                      xmlns:vs="urn:vfi-sapphire:vs.2001-10-01">
     <cookie>SESSION_TOKEN_HEX</cookie>
     <vs:site>1</vs:site>
     <funcList>...</funcList>
   </domain:credential>

2. Fuel prices response (fuel:fuelPrices):
   <fuel:fuelPrices isRtConfig="1"
                    xmlns:vs="urn:vfi-sapphire:vs.2001-10-01"
                    xmlns:fuel="urn:vfi-sapphire:fuel.2001-10-01">
     <vs:site>1</vs:site>
     <fuelSvcModes maxSize="3">
       <fuelSvcMode sysid="1" name="SELF"/>
       <fuelSvcMode sysid="2" name="FULL"/>
       <fuelSvcMode sysid="3" name="MINI"/>
     </fuelSvcModes>
     <fuelMOPs maxSize="2">
       <fuelMOP sysid="1" name="CASH"/>
       <fuelMOP sysid="2" name="CREDIT"/>
     </fuelMOPs>
     <fuelProducts maxSize="20">
       <fuelProduct sysid="1" name="REGULAR" NAXMLFuelGradeID="1">
         <prices>
           <!-- tier 1 = In Effect, tier 2 = Pending -->
           <!-- servLevel: 1=SELF 2=FULL 3=MINI   mop: 1=CASH 2=CREDIT -->
           <price tier="1" servLevel="1" mop="1">5.579</price>
           <price tier="1" servLevel="1" mop="2">5.579</price>
           ...
           <price tier="2" servLevel="1" mop="1">1.112</price>
           <price tier="2" servLevel="1" mop="2">1.122</price>
           ...
         </prices>
       </fuelProduct>
     </fuelProducts>
   </fuel:fuelPrices>

3. Fault response:
   <VFI:Response xmlns:VFI="urn:vfi-sapphire:np.domain.2001-07-01">
     <VFI:Fault>
       <faultCode>CGIPortal.LoginRequired</faultCode>
       <faultString>Session has expired</faultString>
     </VFI:Fault>
   </VFI:Response>

Data model simplification
-------------------------
The raw Commander data has up to 3 service levels x 2 MOPs = 6 price combos
per tier per product.  We simplify to four numbers per grade:
  - in_effect_cash   : Tier 1, CASH (any service level — usually all equal)
  - in_effect_credit : Tier 1, CREDIT
  - pending_cash     : Tier 2, CASH
  - pending_credit   : Tier 2, CREDIT

When writing prices we replicate the single value across all service levels.
"""

from __future__ import annotations

import logging
from typing import Optional
from xml.etree import ElementTree as ET

from models import FuelGrade, FuelGradeTotals, FuelTotals

logger = logging.getLogger(__name__)

# XML namespaces used by the Commander
NS = {
    "fuel": "urn:vfi-sapphire:fuel.2001-10-01",
    "vs":   "urn:vfi-sapphire:vs.2001-10-01",
    "domain": "urn:vfi-sapphire:np.domain.2001-07-01",
    "VFI":  "urn:vfi-sapphire:np.domain.2001-07-01",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_fuel_prices(xml_str: str) -> list[FuelGrade]:
    """
    Parse a vfuelprices (or vfuelrtprices) response into a list of FuelGrade
    objects, one per active product slot (name != "UNUSED").

    Raises ValueError on parse failure.
    """
    xml_str = xml_str.strip()
    if not xml_str:
        raise ValueError("Empty XML response from Commander")

    # Check for fault before expensive parse
    if "<faultCode>" in xml_str:
        fault = _extract_simple(xml_str, "faultCode")
        raise ValueError(f"Commander returned fault: {fault}")

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        raise ValueError(
            f"XML parse error: {e}. Raw (first 500): {xml_str[:500]}"
        ) from e

    grades = _parse_fuel_prices_root(root)
    if not grades:
        logger.warning("No fuel grades found. Root tag: %s. XML: %s", root.tag, xml_str[:500])
        raise ValueError(f"No fuel grades found in response (root: <{root.tag}>)")

    logger.debug("Parsed %d fuel grades", len(grades))
    return grades


def parse_fuel_totals(xml_str: str) -> FuelTotals:
    """
    Parse a vfueltotals response into a FuelTotals object.

    The Commander returns one <fpDispenserData> element per dispenser × grade
    combination. We aggregate volume and revenue by grade name across all
    dispensers.

    Response structure (confirmed on live unit):
        <fuel:fuelTotals ...>
          <vs:period sysid="2" periodType="day" name="Day"
                     periodSeqNum="506"
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

    Raises ValueError on parse failure.
    """
    xml_str = xml_str.strip()
    if not xml_str:
        raise ValueError("Empty XML response from Commander")

    if "<faultCode>" in xml_str:
        fault = _extract_simple(xml_str, "faultCode")
        raise ValueError(f"Commander returned fault: {fault}")

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        raise ValueError(f"XML parse error: {e}. Raw (first 500): {xml_str[:500]}") from e

    # Extract period metadata from <vs:period .../>
    period_el = _find_any(root, "period")
    period_type = ""
    period_label = ""
    period_begin = None
    period_seq_num = None
    site_id = None

    if period_el is not None:
        period_type = period_el.get("periodType", "").lower()
        period_label = period_el.get("name", period_type.title())
        period_begin = period_el.get("periodBeginDate")
        period_seq_num = _safe_int(period_el.get("periodSeqNum"))

    site_el = _find_any(root, "site")
    if site_el is not None:
        site_id = _safe_int(site_el.text)

    # Aggregate fpDispenserData by grade name
    grade_totals: dict[str, dict] = {}  # name -> {volume, money}

    for fp_el in root.iter():
        if _local_name(fp_el.tag) != "fpDispenserData":
            continue

        # productNumber has name attribute
        prod_el = None
        vol_el = None
        mon_el = None
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

        grade_name = prod_el.get("name", "").strip()
        if not grade_name:
            continue

        volume = _safe_float(vol_el.text if vol_el is not None else None) or 0.0
        money = _safe_float(mon_el.text if mon_el is not None else None) or 0.0

        if grade_name not in grade_totals:
            grade_totals[grade_name] = {"volume": 0.0, "money": 0.0}
        grade_totals[grade_name]["volume"] += volume
        grade_totals[grade_name]["money"] += money

    # Build grade objects (sorted by name)
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

    return FuelTotals(
        period_type=period_type,
        period_label=period_label,
        period_begin=period_begin,
        period_seq_num=period_seq_num,
        site_id=site_id,
        grades=grades,
        total_volume_gallons=round(total_volume, 3),
        total_revenue_usd=round(total_revenue, 2),
    )


def parse_session_token(xml_str: str) -> Optional[str]:
    """
    Extract session token from a login (domain:credential) response.

    Returns the hex token string, or None if not found.
    """
    token = _extract_simple(xml_str, "cookie")
    return token if token else None


# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------

def _parse_fuel_prices_root(root: ET.Element) -> list[FuelGrade]:
    """
    Parse <fuel:fuelPrices> (with or without namespace prefix).

    ElementTree strips namespace prefixes in Clark notation, e.g.:
      <fuel:fuelPrices> becomes {urn:vfi-sapphire:fuel.2001-10-01}fuelPrices
    We handle both prefixed and unprefixed tags.
    """
    # Locate fuelProducts container (namespace-agnostic)
    products_el = _find_any(root, "fuelProducts")
    if products_el is None:
        # Try walking down one level in case root IS the fuelPrices element
        products_el = root if root.tag.endswith("fuelProducts") else None

    if products_el is None:
        return []

    grades: list[FuelGrade] = []

    for product_el in products_el:
        tag_local = _local_name(product_el.tag)
        if tag_local != "fuelProduct":
            continue

        sysid = product_el.get("sysid")
        name = product_el.get("name", "").strip()

        if not sysid:
            continue
        if not name or name.upper() == "UNUSED":
            continue

        grade_id = _safe_int(sysid)
        if grade_id is None:
            continue

        # Parse all price entries for this product
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

            # We use SELF (servLevel=1) prices as the canonical price.
            # On most sites all service levels have equal prices.
            if serv_level == 1:
                if tier == 1 and mop == 1:
                    in_effect_cash = value
                elif tier == 1 and mop == 2:
                    in_effect_credit = value
                elif tier == 2 and mop == 1:
                    pending_cash = value
                elif tier == 2 and mop == 2:
                    pending_credit = value

        grade = FuelGrade(
            id=grade_id,
            name=name,
            prices={
                "cash":   in_effect_cash,
                "credit": in_effect_credit,
            },
            pending_prices={
                "cash":   pending_cash,
                "credit": pending_credit,
            },
        )
        grades.append(grade)

    # Sort by grade ID for consistent ordering
    grades.sort(key=lambda g: g.id)
    return grades


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _find_any(root: ET.Element, local_name: str) -> Optional[ET.Element]:
    """Find first element matching local_name, ignoring namespace prefixes."""
    # Try direct find with known namespaces first
    for prefix, ns in NS.items():
        el = root.find(f".//{{{ns}}}{local_name}")
        if el is not None:
            return el
    # Fallback: walk the whole tree
    for el in root.iter():
        if _local_name(el.tag) == local_name:
            return el
    return None


def _local_name(tag: str) -> str:
    """Strip Clark-notation namespace from a tag: {ns}local -> local."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _extract_simple(xml_text: str, tag: str) -> Optional[str]:
    """Fast string extraction of <tag>value</tag> without full XML parse."""
    open_tag = f"<{tag}>"
    close_tag = f"</{tag}>"
    start = xml_text.find(open_tag)
    if start == -1:
        return None
    end = xml_text.find(close_tag, start)
    if end == -1:
        return None
    return xml_text[start + len(open_tag) : end].strip()


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

"""
NAXML builder for Verifone Commander request bodies.

All Commander calls use:
  POST https://<host>/cgi-bin/NAXML?
  Content-Type: application/x-www-form-urlencoded
  Body: cmd=<command>&[cookie=<token>]&...\n\n[<optional_xml>]

This module builds the body strings and the XML payloads for write operations.

Confirmed request formats (from live GWT interception):
  Login:  cmd=validate&user=<u>&passwd=<p>\n\n
  Read:   cmd=vfuelprices&cookie=<token>\n\n
  Write:  cmd=ufuelprices&cookie=<token>\n\n<fuel_prices_xml>
  Push:   cmd=cfuelprices&cookie=<token>\n\n

Write XML format (sent to ufuelprices):
  The XML mirrors the vfuelprices response structure, sending Tier 2 (Pending)
  prices for each product.  Service levels are set to the same value.

  <fuel:fuelPrices xmlns:vs="urn:vfi-sapphire:vs.2001-10-01"
                   xmlns:fuel="urn:vfi-sapphire:fuel.2001-10-01">
    <vs:site>1</vs:site>
    <fuelProducts>
      <fuelProduct sysid="1" name="REGULAR" NAXMLFuelGradeID="1">
        <prices>
          <price tier="2" servLevel="1" mop="1">4.999</price>
          <price tier="2" servLevel="1" mop="2">5.099</price>
          <price tier="2" servLevel="2" mop="1">4.999</price>
          <price tier="2" servLevel="2" mop="2">5.099</price>
          <price tier="2" servLevel="3" mop="1">4.999</price>
          <price tier="2" servLevel="3" mop="2">5.099</price>
        </prices>
      </fuelProduct>
    </fuelProducts>
  </fuel:fuelPrices>
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

from models import FuelGrade, GradePriceUpdate

logger = logging.getLogger(__name__)

# Namespace URIs discovered on the live unit
NS_FUEL = "urn:vfi-sapphire:fuel.2001-10-01"
NS_VS   = "urn:vfi-sapphire:vs.2001-10-01"

# Service levels supported by the Commander
SERVICE_LEVELS = [1, 2, 3]  # 1=SELF, 2=FULL, 3=MINI

# MOPs
MOP_CASH   = 1
MOP_CREDIT = 2


# ---------------------------------------------------------------------------
# Request body builders
# ---------------------------------------------------------------------------

def build_login_body(username: str, password: str) -> str:
    """
    Build the form-encoded login request body.

    Confirmed format from live GWT interception:
      cmd=validate&user=manager&passwd=Raffik15\n\n
    """
    return f"cmd=validate&user={username}&passwd={password}\n\n"


def build_read_body(token: str, cmd: str = "vfuelprices") -> str:
    """
    Build a read request body.

      cmd=vfuelprices&cookie=<token>\n\n
    """
    return f"cmd={cmd}&cookie={token}\n\n"


def build_write_body(token: str, price_xml: str) -> str:
    """
    Build a write (ufuelprices) request body with XML payload.

      cmd=ufuelprices&cookie=<token>\n\n<xml>
    """
    return f"cmd=ufuelprices&cookie={token}\n\n{price_xml}"


def build_push_body(token: str) -> str:
    """
    Build the push-to-dispensers (cfuelprices) request body.

      cmd=cfuelprices&cookie=<token>\n\n
    """
    return f"cmd=cfuelprices&cookie={token}\n\n"


# ---------------------------------------------------------------------------
# XML builders for write payloads
# ---------------------------------------------------------------------------

def build_price_xml(updates: list[GradePriceUpdate], site_id: int = 1) -> str:
    """
    Build the fuel:fuelPrices XML payload for the ufuelprices command.

    Sets Tier 2 (Pending) prices.  Each cash/credit value is replicated
    across all service levels (SELF, FULL, MINI) since the Commander UI
    treats them as a single price per MOP.

    Args:
        updates:  List of grade updates with id, name, cash, credit.
                  Pass None for cash or credit to skip that MOP.
        site_id:  Site identifier (default 1).

    Returns:
        XML string to append after the NAXML body header.
    """
    # Register namespaces to get readable output
    ET.register_namespace("fuel", NS_FUEL)
    ET.register_namespace("vs",   NS_VS)

    root = ET.Element(f"{{{NS_FUEL}}}fuelPrices")
    site_el = ET.SubElement(root, f"{{{NS_VS}}}site")
    site_el.text = str(site_id)

    products_el = ET.SubElement(root, "fuelProducts")

    for update in updates:
        product_el = ET.SubElement(products_el, "fuelProduct")
        product_el.set("sysid", str(update.id))
        product_el.set("name", update.name)
        product_el.set("NAXMLFuelGradeID", str(update.id))

        prices_el = ET.SubElement(product_el, "prices")

        # Tier 2 (Pending) prices, all service levels
        for svc in SERVICE_LEVELS:
            if update.cash is not None:
                p = ET.SubElement(prices_el, "price")
                p.set("tier", "2")
                p.set("servLevel", str(svc))
                p.set("mop", str(MOP_CASH))
                p.text = f"{update.cash:.3f}"

            if update.credit is not None:
                p = ET.SubElement(prices_el, "price")
                p.set("tier", "2")
                p.set("servLevel", str(svc))
                p.set("mop", str(MOP_CREDIT))
                p.text = f"{update.credit:.3f}"

    ET.indent(root, space="  ")
    xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
    logger.debug("Built price XML (%d grades): %s", len(updates), xml_str[:300])
    return xml_str


def build_price_xml_from_grades(grades: list[FuelGrade]) -> str:
    """
    Build a write payload from full FuelGrade objects.

    Uses each grade's pending_prices if available, otherwise falls back to prices.
    Useful for re-pushing all current prices.
    """
    updates = []
    for g in grades:
        src = g.pending_prices if g.pending_prices else g.prices
        updates.append(GradePriceUpdate(
            id=g.id,
            name=g.name,
            cash=src.get("cash"),
            credit=src.get("credit"),
        ))
    return build_price_xml(updates)

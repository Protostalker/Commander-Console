"""
Async HTTP client for the Verifone Commander NAXML CGI API.

Discovered via live inspection of smincgs.ddns.net:

  Endpoint:  POST https://<host>/cgi-bin/NAXML?
  Encoding:  application/x-www-form-urlencoded
  Body fmt:  cmd=<command>&[cookie=<token>&]...\n\n[<optional_xml>]

Session token architecture
--------------------------
1. Login once:  POST body = "cmd=validate&user=<u>&passwd=<p>\n\n"
   Response:    <domain:credential>...<cookie>TOKEN</cookie>...</domain:credential>
2. All other calls include the token:
               "cmd=vfuelprices&cookie=TOKEN\n\n"
3. If response contains <faultCode>CGIPortal.LoginRequired</faultCode>,
   re-login and retry automatically.
4. Token is refreshed proactively every REFRESH_INTERVAL_HOURS (default 23h)
   so sessions never silently expire between requests.

Key commands discovered on the live unit:
  vfuelprices   — read In-Effect + Pending prices
  vfuelrtprices — read real-time dispenser prices
  ufuelprices   — write Pending prices (POST with XML body)
  cfuelprices   — commit Pending -> In-Effect (push to dispensers)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

NAXML_PATH = "/cgi-bin/NAXML?"

# Commander session lifetime is observed to be ~30 minutes or less.
# We treat tokens as stale after 25 minutes and re-login proactively.
# This is a "login on demand" model — no background keep-alive needed.
# The flow is: check token age before every call → re-login if stale →
# if LoginRequired fault still comes back mid-call → re-login and retry once.
REFRESH_INTERVAL_SECONDS = 25 * 60  # 25 minutes

# Fault code indicating session expiry
FAULT_LOGIN_REQUIRED = "CGIPortal.LoginRequired"


class CommanderAuthError(Exception):
    """Raised when login to Commander fails."""


class CommanderConnectionError(Exception):
    """Raised when a NAXML command fails."""


class CommanderFaultError(Exception):
    """Raised when Commander returns a NAXML fault response."""
    def __init__(self, fault_code: str, fault_string: str = "") -> None:
        self.fault_code = fault_code
        self.fault_string = fault_string
        super().__init__(f"Commander fault: {fault_code} -- {fault_string}")


class CommanderClient:
    """
    Async HTTP client for the Verifone Commander NAXML CGI API.

    Thread-safety: designed for a single asyncio event loop. Create one
    instance per application and reuse it.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        verify_ssl: bool = False,
        timeout: int = 10,
        retry_attempts: int = 3,
    ) -> None:
        self.base_url = f"https://{host}:{port}"
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.retry_attempts = retry_attempts

        self._client: Optional[httpx.AsyncClient] = None
        self._session_token: Optional[str] = None
        self._token_acquired_at: float = 0.0   # epoch seconds
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        return self._session_token is not None

    @property
    def token_age_seconds(self) -> float:
        if not self._session_token:
            return float("inf")
        return time.time() - self._token_acquired_at

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    # ------------------------------------------------------------------
    # Internal HTTP client
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                verify=self.verify_ssl,
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def login(self) -> bool:
        """
        POST credentials to obtain a session token.

        Body: cmd=validate&user=<username>&passwd=<password>\n\n
        Response: <domain:credential>...<cookie>TOKEN</cookie>...</domain:credential>

        Returns True on success, False if login fails.
        """
        client = await self._get_client()
        url = f"{self.base_url}{NAXML_PATH}"

        # Body format confirmed via live GWT interception
        body = f"cmd=validate&user={self.username}&passwd={self.password}\n\n"

        try:
            resp = await client.post(
                url,
                content=body.encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.RequestError as e:
            msg = f"Commander login request failed: {e}"
            logger.error(msg)
            self._last_error = msg
            return False

        if resp.status_code != 200:
            msg = f"Commander login HTTP {resp.status_code}"
            logger.error(msg)
            self._last_error = msg
            return False

        # Parse the session token from the response XML
        token = _extract_session_token(resp.text)
        if not token:
            msg = f"Commander login: no <cookie> token in response. Body: {resp.text[:300]}"
            logger.error(msg)
            self._last_error = msg
            return False

        self._session_token = token
        self._token_acquired_at = time.time()
        self._last_error = None
        logger.info(
            "Commander login succeeded -- token acquired (refresh in %dh)",
            REFRESH_INTERVAL_SECONDS // 3600,
        )
        return True

    async def _ensure_token(self) -> str:
        """
        Return a valid session token, logging in if needed.

        Proactively refreshes if token is older than REFRESH_INTERVAL_SECONDS.
        Raises CommanderAuthError if login fails.
        """
        needs_refresh = (
            not self._session_token
            or self.token_age_seconds >= REFRESH_INTERVAL_SECONDS
        )
        if needs_refresh:
            reason = "no token" if not self._session_token else "token aged out"
            logger.info("Session refresh triggered (%s)", reason)
            ok = await self.login()
            if not ok:
                raise CommanderAuthError(
                    f"Cannot authenticate with Commander at {self.base_url}: "
                    f"{self._last_error}"
                )
        return self._session_token  # type: ignore[return-value]

    def _invalidate_token(self) -> None:
        """Force re-login on next call."""
        self._session_token = None
        self._token_acquired_at = 0.0

    # ------------------------------------------------------------------
    # Core NAXML dispatcher
    # ------------------------------------------------------------------

    async def _naxml(self, cmd: str, xml_body: str = "") -> str:
        """
        Send one NAXML POST request.

        Body format:
            cmd=<cmd>&cookie=<token>\n\n[<xml_body>]

        On CGIPortal.LoginRequired fault: re-logs in and retries once.
        """
        client = await self._get_client()
        url = f"{self.base_url}{NAXML_PATH}"

        for attempt in range(2):  # 0 = first try, 1 = after re-login
            token = await self._ensure_token()
            body = f"cmd={cmd}&cookie={token}\n\n{xml_body}"

            try:
                resp = await client.post(
                    url,
                    content=body.encode("utf-8"),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            except httpx.RequestError as e:
                msg = f"NAXML {cmd} request error: {e}"
                logger.error(msg)
                self._last_error = msg
                raise CommanderConnectionError(msg) from e

            if resp.status_code != 200:
                msg = f"NAXML {cmd} HTTP {resp.status_code}"
                logger.error(msg)
                self._last_error = msg
                raise CommanderConnectionError(msg)

            text = resp.text

            # Check for fault response
            fault_code = _extract_fault_code(text)
            if fault_code:
                fault_str = _extract_fault_string(text)

                if fault_code == FAULT_LOGIN_REQUIRED and attempt == 0:
                    logger.info(
                        "NAXML %s: session expired (LoginRequired), re-authenticating", cmd
                    )
                    self._invalidate_token()
                    continue  # retry with fresh token

                self._last_error = f"{fault_code}: {fault_str}"
                raise CommanderFaultError(fault_code, fault_str)

            self._last_error = None
            return text

        # Should not reach here
        raise CommanderConnectionError(f"NAXML {cmd} failed after re-login")

    # ------------------------------------------------------------------
    # Fuel price operations
    # ------------------------------------------------------------------

    async def get_fuel_prices(self) -> str:
        """
        Read current In-Effect and Pending fuel prices.

        Returns raw NAXML XML (fuel:fuelPrices).
        Commander command: vfuelprices
        """
        return await self._naxml("vfuelprices")

    async def get_realtime_prices(self) -> str:
        """
        Read real-time prices currently shown on the dispensers.

        May differ from Commander DB prices if a push is pending.
        Commander command: vfuelrtprices
        """
        return await self._naxml("vfuelrtprices")

    async def update_prices(self, naxml_xml: str) -> str:
        """
        Write Pending price updates to the Commander database.

        This does NOT push to physical dispensers. Call push_prices_to_dispensers()
        after to make prices live at the pump.

        Args:
            naxml_xml: XML built by naxml_builder.build_price_xml()

        Commander command: ufuelprices
        """
        return await self._naxml("ufuelprices", xml_body=naxml_xml)

    async def push_prices_to_dispensers(self) -> str:
        """
        Commit Pending -> In-Effect, pushing to physical dispensers.

        Call after update_prices() to make changes visible at the pump.
        Commander command: cfuelprices
        """
        return await self._naxml("cfuelprices")

    async def get_fuel_totals(self, period: int = 2) -> str:
        """
        Read sales totals for a given period.

        period values (confirmed on live unit):
          1 = Shift  (current daypart)
          2 = Day    (today)
          3 = Month  (current calendar month)
          4 = Year   (current year)

        The period must be passed as a URL param in the body (not XML).
        Body format: cmd=vfueltotals&cookie=TOKEN&period=N\n\n

        Commander command: vfueltotals
        """
        # period param must be appended directly to the cmd line, not XML body
        client = await self._get_client()
        url = f"{self.base_url}{NAXML_PATH}"

        for attempt in range(2):
            token = await self._ensure_token()
            body = f"cmd=vfueltotals&cookie={token}&period={period}\n\n"

            try:
                resp = await client.post(
                    url,
                    content=body.encode("utf-8"),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            except httpx.RequestError as e:
                msg = f"vfueltotals request error: {e}"
                logger.error(msg)
                self._last_error = msg
                raise CommanderConnectionError(msg) from e

            if resp.status_code != 200:
                msg = f"vfueltotals HTTP {resp.status_code}"
                logger.error(msg)
                self._last_error = msg
                raise CommanderConnectionError(msg)

            text = resp.text
            fault_code = _extract_fault_code(text)
            if fault_code:
                fault_str = _extract_fault_string(text)
                if fault_code == FAULT_LOGIN_REQUIRED and attempt == 0:
                    logger.info("vfueltotals: session expired, re-authenticating")
                    self._invalidate_token()
                    continue
                self._last_error = f"{fault_code}: {fault_str}"
                raise CommanderFaultError(fault_code, fault_str)

            self._last_error = None
            return text

        raise CommanderConnectionError("vfueltotals failed after re-login")

    async def ping(self) -> bool:
        """
        Test connectivity by attempting to login.

        Returns True if the Commander is reachable and credentials are valid.
        Does not raise -- returns False on failure.
        """
        try:
            return await self.login()
        except Exception as e:
            logger.warning("Commander ping failed: %s", e)
            self._last_error = str(e)
            return False

    # ------------------------------------------------------------------
    # Daily refresh scheduling
    # ------------------------------------------------------------------

    async def run_session_refresh(self) -> None:
        """
        Background coroutine that proactively re-logins before the token
        expires. Sleeps REFRESH_INTERVAL_SECONDS (25 min) between refreshes.

        Commander sessions expire in ~30 minutes. This is a lightweight
        "login on demand" approach — we don't hold a persistent session,
        we just ensure the token is fresh before each call. This background
        task is optional; _ensure_token() handles stale tokens per-request
        regardless. Run this only if you want to avoid the latency of
        a re-login on the first call after a quiet period.

        Example:
            asyncio.create_task(client.run_session_refresh())
        """
        while True:
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
            logger.info(
                "Proactive session refresh (token age threshold: %dm)",
                REFRESH_INTERVAL_SECONDS // 60,
            )
            try:
                ok = await self.login()
                if ok:
                    logger.debug("Session refresh succeeded")
                else:
                    logger.warning("Session refresh failed: %s", self._last_error)
            except Exception as e:
                logger.warning("Session refresh exception: %s", e)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client and release connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._invalidate_token()
        logger.debug("CommanderClient closed")


# ------------------------------------------------------------------
# XML helpers (kept here to avoid circular imports with naxml_parser)
# ------------------------------------------------------------------

def _extract_session_token(xml_text: str) -> Optional[str]:
    """
    Extract <cookie>TOKEN</cookie> from a Commander login response.

    Login response structure:
      <domain:credential xmlns:domain="urn:vfi-sapphire:np.domain.2001-07-01" ...>
        <cookie>40596f0dd65b38f31a8e7d566dcdcdf</cookie>
        <vs:site>1</vs:site>
        <funcList>...</funcList>
      </domain:credential>
    """
    start = xml_text.find("<cookie>")
    if start == -1:
        return None
    end = xml_text.find("</cookie>", start)
    if end == -1:
        return None
    token = xml_text[start + 8 : end].strip()
    return token if token else None


def _extract_fault_code(xml_text: str) -> Optional[str]:
    """
    Extract <faultCode>...</faultCode> from a NAXML fault response.

    Fault response format:
      <VFI:Response xmlns:VFI="urn:vfi-sapphire:np.domain.2001-07-01">
        <VFI:Fault>
          <faultCode>CGIPortal.LoginRequired</faultCode>
          <faultString>Session expired</faultString>
        </VFI:Fault>
      </VFI:Response>
    """
    start = xml_text.find("<faultCode>")
    if start == -1:
        return None
    end = xml_text.find("</faultCode>", start)
    if end == -1:
        return None
    return xml_text[start + 11 : end].strip()


def _extract_fault_string(xml_text: str) -> str:
    """Extract <faultString>...</faultString> from a fault response."""
    start = xml_text.find("<faultString>")
    if start == -1:
        return ""
    end = xml_text.find("</faultString>", start)
    if end == -1:
        return ""
    return xml_text[start + 13 : end].strip()

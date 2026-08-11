"""
Async NAXML HTTP client for the Verifone Commander CGI API -- READ ONLY.

Forked from commander-console/connector/commander_client.py. All write
commands (ufuelprices, cfuelprices) have been deleted, not just unused --
they do not appear anywhere in this file or this project. This client can
only ever call: validate, vfuelprices, vfueltotals, vmaintfprht, vfuelcfg.

Protocol notes (confirmed against a live Commander unit):
  Endpoint:  POST https://<host>:<port>/cgi-bin/NAXML?
  Encoding:  application/x-www-form-urlencoded
  Login:     cmd=validate&user=<u>&passwd=<p>\\n\\n
             -> <domain:credential>...<cookie>TOKEN</cookie>...</domain:credential>
  Auth call: cmd=<command>&cookie=<token>[&extra=params]\\n\\n[<xml_body>]
             The trailing \\n\\n is mandatory -- it separates the URL-encoded
             header from an optional XML body.
  Params like `period` for vfueltotals go in the body header, NOT in XML.
  Session expiry: <faultCode>CGIPortal.LoginRequired</faultCode>
    -> re-login once, retry the original request.
  SSL cert is self-signed -> verify=False by default.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

NAXML_PATH = "/cgi-bin/NAXML?"
FAULT_LOGIN_REQUIRED = "CGIPortal.LoginRequired"


class CommanderAuthError(Exception):
    """Raised when login to Commander fails."""


class CommanderConnectionError(Exception):
    """Raised when a NAXML command fails at the transport/HTTP level."""


class CommanderFaultError(Exception):
    """Raised when Commander returns a NAXML fault response."""

    def __init__(self, fault_code: str, fault_string: str = "") -> None:
        self.fault_code = fault_code
        self.fault_string = fault_string
        super().__init__(f"Commander fault: {fault_code} -- {fault_string}")


class CommanderClient:
    """
    Read-only async client for the Verifone Commander NAXML CGI API.

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
        session_refresh_minutes: int = 25,
    ) -> None:
        self.base_url = f"https://{host}:{port}"
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.refresh_interval_seconds = session_refresh_minutes * 60

        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None
        self._token_at: float = 0.0
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None

    @property
    def token_age_seconds(self) -> float:
        if not self._token:
            return float("inf")
        return time.time() - self._token_at

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
        """POST credentials to obtain a session token. Returns True on success."""
        client = await self._get_client()
        url = f"{self.base_url}{NAXML_PATH}"
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

        token = _extract_tag(resp.text, "cookie")
        if not token:
            msg = f"Commander login: no <cookie> token in response. Body: {resp.text[:300]}"
            logger.error(msg)
            self._last_error = msg
            return False

        self._token = token
        self._token_at = time.time()
        self._last_error = None
        logger.info("Commander login succeeded -- token acquired")
        return True

    async def _ensure_token(self) -> str:
        needs_refresh = (
            not self._token or self.token_age_seconds >= self.refresh_interval_seconds
        )
        if needs_refresh:
            reason = "no token" if not self._token else "token aged out"
            logger.info("Session refresh triggered (%s)", reason)
            ok = await self.login()
            if not ok:
                raise CommanderAuthError(
                    f"Cannot authenticate with Commander at {self.base_url}: {self._last_error}"
                )
        return self._token  # type: ignore[return-value]

    def _invalidate_token(self) -> None:
        self._token = None
        self._token_at = 0.0

    # ------------------------------------------------------------------
    # Core NAXML dispatcher
    # ------------------------------------------------------------------

    async def _naxml(self, cmd: str, xml_body: str = "", **params) -> str:
        """
        Send one NAXML POST request.

        Body format: cmd=<cmd>&cookie=<token>[&k=v ...]\\n\\n[<xml_body>]
        Extra keyword args are appended as body params (e.g. period=2 for
        vfueltotals) -- NOT placed in the XML body, per Commander's format.

        On CGIPortal.LoginRequired: re-logs in and retries once.
        """
        client = await self._get_client()
        url = f"{self.base_url}{NAXML_PATH}"
        extra = "".join(f"&{k}={v}" for k, v in params.items())

        for attempt in range(2):  # 0 = first try, 1 = after re-login
            token = await self._ensure_token()
            body = f"cmd={cmd}&cookie={token}{extra}\n\n{xml_body}"

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
            fault_code = _extract_tag(text, "faultCode")
            if fault_code:
                fault_str = _extract_tag(text, "faultString") or ""

                if fault_code == FAULT_LOGIN_REQUIRED and attempt == 0:
                    logger.info("NAXML %s: session expired, re-authenticating", cmd)
                    self._invalidate_token()
                    continue

                self._last_error = f"{fault_code}: {fault_str}"
                raise CommanderFaultError(fault_code, fault_str)

            self._last_error = None
            return text

        raise CommanderConnectionError(f"NAXML {cmd} failed after re-login")

    # ------------------------------------------------------------------
    # Read-only Commander commands
    # ------------------------------------------------------------------
    # DO NOT add ufuelprices, cfuelprices, ccarwashenable/disable, or any
    # other write/"c"/"u"-prefixed command to this class. That is the one
    # hard constraint of this project.

    async def get_fuel_prices(self) -> str:
        """vfuelprices -- In-Effect + Pending prices for all grades."""
        return await self._naxml("vfuelprices")

    async def get_fuel_totals(self, period: int = 2) -> str:
        """
        vfueltotals&period=N -- volume + revenue per dispenser/grade.
        period: 1=Shift, 2=Day, 3=Month, 4=Year
        """
        return await self._naxml("vfueltotals", period=period)

    async def get_pump_totals(self) -> str:
        """vmaintfprht -- lifetime mechanical totals per pump/hose."""
        return await self._naxml("vmaintfprht")

    async def get_fuel_config(self) -> str:
        """vfuelcfg -- site fuel configuration (grades, UOM, service levels)."""
        return await self._naxml("vfuelcfg")

    async def ping(self) -> bool:
        """Test connectivity by attempting to login. Never raises."""
        try:
            return await self.login()
        except Exception as e:
            logger.warning("Commander ping failed: %s", e)
            self._last_error = str(e)
            return False

    # ------------------------------------------------------------------
    # Background session refresh
    # ------------------------------------------------------------------

    async def run_session_refresh(self) -> None:
        """
        Proactively re-login before the ~30 minute Commander session expires.
        _ensure_token() also handles stale tokens per-request, so this task
        is a latency optimization, not a correctness requirement.
        """
        while True:
            await asyncio.sleep(self.refresh_interval_seconds)
            logger.info(
                "Proactive session refresh (interval: %dm)",
                self.refresh_interval_seconds // 60,
            )
            try:
                ok = await self.login()
                if not ok:
                    logger.warning("Session refresh failed: %s", self._last_error)
            except Exception as e:
                logger.warning("Session refresh exception: %s", e)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._invalidate_token()
        logger.debug("CommanderClient closed")


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def _extract_tag(xml_text: str, tag: str) -> Optional[str]:
    """Fast string extraction of <tag>value</tag> without a full XML parse."""
    start = xml_text.find(f"<{tag}>")
    if start == -1:
        return None
    end = xml_text.find(f"</{tag}>", start)
    if end == -1:
        return None
    return xml_text[start + len(tag) + 2 : end].strip()

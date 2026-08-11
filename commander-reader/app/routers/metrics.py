"""GET /metrics -- Prometheus-compatible text exposition format."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse, summary="Prometheus-compatible metrics")
async def metrics(request: Request) -> str:
    state = request.app.state
    cache = state.price_cache
    client = state.commander_client
    grades = cache.grades or []

    lines: list[str] = []

    lines.append("# HELP commander_price_cash Current in-effect cash price per gallon")
    lines.append("# TYPE commander_price_cash gauge")
    for g in grades:
        if g.in_effect.cash is not None:
            lines.append(f'commander_price_cash{{grade="{_esc(g.name)}"}} {g.in_effect.cash}')

    lines.append("# HELP commander_price_credit Current in-effect credit price per gallon")
    lines.append("# TYPE commander_price_credit gauge")
    for g in grades:
        if g.in_effect.credit is not None:
            lines.append(f'commander_price_credit{{grade="{_esc(g.name)}"}} {g.in_effect.credit}')

    lines.append("# HELP commander_session_age_seconds Age of the current Commander session token")
    lines.append("# TYPE commander_session_age_seconds gauge")
    session_age = client.token_age_seconds if client.is_authenticated else -1
    lines.append(f"commander_session_age_seconds {session_age}")

    lines.append("# HELP commander_last_fetch_age_seconds Seconds since the last successful price fetch")
    lines.append("# TYPE commander_last_fetch_age_seconds gauge")
    fetch_age = cache.age_seconds()
    lines.append(f"commander_last_fetch_age_seconds {fetch_age if fetch_age is not None else -1}")

    lines.append("# HELP commander_connected Whether the last Commander communication succeeded (1=yes, 0=no)")
    lines.append("# TYPE commander_connected gauge")
    lines.append(f"commander_connected {1 if state.connection_healthy else 0}")

    return "\n".join(lines) + "\n"


def _esc(label: str) -> str:
    return label.replace("\\", "\\\\").replace('"', '\\"')

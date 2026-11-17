"""
Configuration loader for commander-console.

Reads config/commander.yaml and merges in environment variables.
The COMMANDER_PASSWORD env var always overrides the yaml value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CommanderConfig:
    host: str
    port: int
    https: bool
    verify_ssl: bool
    username: str
    password: str
    timeout_seconds: int
    session_retry_attempts: int
    # Circuit breaker — see commander_client.py's is_locked_out. Default 3
    # is well under the Commander unit's own login-attempt lockout (~10).
    lockout_threshold: int = 3


@dataclass
class PollingConfig:
    price_poll_interval_seconds: int


@dataclass
class MockGrade:
    id: int
    name: str
    cash_price: float
    credit_price: float


@dataclass
class MockConfig:
    enabled: bool
    grades: list[MockGrade] = field(default_factory=list)


@dataclass
class AppConfig:
    commander: CommanderConfig
    polling: PollingConfig
    mock: MockConfig


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """
    Load configuration from YAML file, then apply environment variable overrides.

    Searches for config in:
      1. The explicit path passed in
      2. /app/config/commander.yaml  (Docker volume mount)
      3. ./config/commander.yaml     (local dev)
    """
    if config_path is None:
        candidates = [
            Path("/app/config/commander.yaml"),
            Path("config/commander.yaml"),
        ]
        for candidate in candidates:
            if candidate.exists():
                config_path = candidate
                break
        else:
            raise FileNotFoundError(
                "Could not find commander.yaml. "
                "Tried: " + ", ".join(str(c) for c in candidates)
            )

    with open(config_path) as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    c = raw.get("commander", {})
    commander = CommanderConfig(
        host=c.get("host", "127.0.0.1"),
        port=int(c.get("port", 443)),
        https=bool(c.get("https", True)),
        verify_ssl=bool(c.get("verify_ssl", False)),
        username=c.get("username", "service"),
        # env var COMMANDER_PASSWORD always wins
        password=os.environ.get("COMMANDER_PASSWORD") or c.get("password", ""),
        timeout_seconds=int(c.get("timeout_seconds", 10)),
        session_retry_attempts=int(c.get("session_retry_attempts", 3)),
        lockout_threshold=int(os.environ.get("COMMANDER_LOCKOUT_THRESHOLD") or c.get("lockout_threshold", 3)),
    )

    p = raw.get("polling", {})
    polling = PollingConfig(
        price_poll_interval_seconds=int(p.get("price_poll_interval_seconds", 60)),
    )

    m = raw.get("mock", {})
    mock_grades = [
        MockGrade(
            id=g["id"],
            name=g["name"],
            cash_price=float(g.get("cash_price", 0.0)),
            credit_price=float(g.get("credit_price", 0.0)),
        )
        for g in m.get("grades", [])
    ]
    mock = MockConfig(
        enabled=bool(m.get("enabled", False)),
        grades=mock_grades,
    )

    return AppConfig(commander=commander, polling=polling, mock=mock)

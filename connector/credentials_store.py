"""
Persisted override for the Commander username/password, separate from
commander.yaml / COMMANDER_PASSWORD.

Why this exists: the normal config path requires editing a file (or env
var) and restarting the container to pick up a rotated Commander password
-- easy to forget, which is exactly how a stale password sits there
silently until the login circuit breaker (or worse, the Commander's own
lockout) trips. POST /api/credentials updates the *running* service
immediately and persists the change here so it survives a restart too,
without ever touching the repo, commander.yaml, or .env.

The file lives in the `ccdata` Docker volume (mounted at /app/data, see
docker-compose.yml) -- it never enters the git repo, so there's nothing for
.gitignore to need to cover.
"""
from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PATH = Path("/app/data/commander_credentials.json")


def load() -> Optional[tuple[str, str]]:
    """Returns (username, password) if an override has been saved, else None."""
    if not _PATH.exists():
        return None
    try:
        data = json.loads(_PATH.read_text())
        return data["username"], data["password"]
    except Exception as e:
        logger.warning("Could not read saved Commander credentials (%s) -- ignoring override", e)
        return None


def save(username: str, password: str) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps({"username": username, "password": password}))
    os.chmod(_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600 -- owner read/write only
    logger.info("Commander credentials override saved for user %r (password not logged)", username)

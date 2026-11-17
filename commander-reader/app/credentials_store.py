"""
Persisted override for the Commander username/password, separate from the
env-var-sourced Settings.

Why this exists: COMMANDER_PASSWORD normally comes from .env, which means
updating it after rotating the password on the Commander console itself
required editing a file and restarting the container -- easy to forget,
which is exactly how a stale password sits there silently until the login
circuit breaker (or worse, the Commander's own lockout) trips. This lets
POST /config/credentials update the *running* service immediately, and
persists the change to the same Docker volume as history.db so it survives
a restart too, without ever touching the repo or .env.

The file lives outside the git repo entirely (a named Docker volume mounted
at /app/data, see docker-compose.yml) -- there is nothing here for
.gitignore to need to cover. Permissions are tightened to owner-only on
write, same spirit as a private key.
"""
from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _path(db_path: str) -> Path:
    return Path(db_path).parent / "commander_credentials.json"


def load(db_path: str) -> Optional[tuple[str, str]]:
    """Returns (username, password) if an override has been saved, else None."""
    p = _path(db_path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return data["username"], data["password"]
    except Exception as e:
        logger.warning("Could not read saved Commander credentials (%s) -- ignoring override", e)
        return None


def save(db_path: str, username: str, password: str) -> None:
    p = _path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"username": username, "password": password}))
    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)  # 0600 -- owner read/write only
    logger.info("Commander credentials override saved for user %r (password not logged)", username)

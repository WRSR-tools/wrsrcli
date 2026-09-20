"""Persistent config in %APPDATA%\\wrsrcli\\config.json.

Never stored inside the repo (SPEC.md 3) — this holds the Steam Web API
the resolved game/workshop paths.
"""

import json
import os
from pathlib import Path

from .errors import WrsrcliError

GAME_PATH = "game_path"
WORKSHOP_PATH = "workshop_path"


def config_dir():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise WrsrcliError("APPDATA is not set — cannot locate the config directory.")
    return Path(appdata) / "wrsrcli"


def config_path():
    return config_dir() / "config.json"


def manifest_path():
    """Where `scan` writes and `output-table` reads (decision D-003)."""
    return config_dir() / "manifest.json"


def load():
    """Read config.json. A missing file is normal — it means nothing is set yet."""
    path = config_path()
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise WrsrcliError(f"could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WrsrcliError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise WrsrcliError(f"{path} should contain a JSON object.")
    return data


def save(data):
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise WrsrcliError(f"could not write {path}: {exc}") from exc


def get(key):
    return load().get(key)


def set_value(key, value):
    data = load()
    data[key] = value
    save(data)


def remove(key):
    """Remove `key`. Returns True if it was there."""
    data = load()
    if key not in data:
        return False
    del data[key]
    save(data)
    return True

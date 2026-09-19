"""Tracking which import lists have been run (decision D-011).

SPEC.md 4.6 requires `manual-rerun` to replay previously-run import lists,
but 5's backup manifest records only what was overwritten or removed --
never the source a file was copied from. So each run registers itself here
and keeps a verbatim copy of the list, which is what gets replayed.

    %APPDATA%\\wrsrcli\\imports.json
    %APPDATA%\\wrsrcli\\imports\\{origin}\\{stamp}.yaml
"""

import datetime
import json
import shutil

from . import config
from .errors import WrsrcliError


def registry_path():
    return config.config_dir() / "imports.json"


def store_root():
    return config.config_dir() / "imports"


def load():
    path = registry_path()
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise WrsrcliError(f"could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WrsrcliError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise WrsrcliError(f"{path} should contain a JSON array of entries.")
    return data


def save(entries):
    path = registry_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise WrsrcliError(f"could not write {path}: {exc}") from exc


def register(list_path, origin_steamid, stamp):
    """Record a run and keep a copy of the list it used."""
    origin_steamid = str(origin_steamid)
    stored = store_root() / origin_steamid / f"{stamp}.yaml"

    try:
        stored.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(list_path, stored)
    except OSError as exc:
        raise WrsrcliError(f"could not store a copy of {list_path}: {exc}") from exc

    entry = {
        "origin_steamid": origin_steamid,
        "stamp": stamp,
        "list_path": str(list_path),
        "stored_list": str(stored),
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    entries = load()
    entries.append(entry)
    save(entries)
    return entry


def latest_per_origin():
    """The most recent registration for each origin item (decision D-011)."""
    newest = {}
    for entry in load():
        origin = entry.get("origin_steamid")
        if not origin:
            continue
        current = newest.get(origin)
        if current is None or entry.get("stamp", "") >= current.get("stamp", ""):
            newest[origin] = entry
    return newest

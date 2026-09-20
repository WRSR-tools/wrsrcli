"""What `wrsrcli update` has fetched (decision D-021).

Items placed in Steam's workshop folder by `update` have no `.acf` entry,
so Steam holds no record of which version is on disk. This file is that
record: `%APPDATA%\\wrsrcli\\downloads.json`, mapping item id to the
workshop `time_updated` of the version fetched.

It is kept apart from `config.json` (user settings) and from
`manifest.json` (rebuilt wholesale by every scan) because it is neither —
it is the tool's own bookkeeping, and losing it only costs the ability to
tell whether an item `update` placed has since gone out of date.
"""

import datetime
import json

from . import config
from .errors import WrsrcliError

FILENAME = "downloads.json"


def path():
    return config.config_dir() / FILENAME


def load():
    """{item_id: {"time_updated": str, "downloaded_at": str}}."""
    target = path()
    if not target.exists():
        return {}
    try:
        with target.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise WrsrcliError(f"could not read {target}: {exc}") from exc
    except json.JSONDecodeError:
        # Our own file, and only a convenience: a corrupt one costs staleness
        # detection for update-placed items, not the command.
        return {}
    return data if isinstance(data, dict) else {}


def record(item_id, time_updated):
    """Note that `item_id` is on disk at version `time_updated`."""
    data = load()
    data[str(item_id)] = {
        "time_updated": str(time_updated) if time_updated else None,
        "downloaded_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    target = path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise WrsrcliError(f"could not write {target}: {exc}") from exc
    return target


def version_of(item_id):
    """The recorded `time_updated` for an item, or None."""
    return (load().get(str(item_id)) or {}).get("time_updated")

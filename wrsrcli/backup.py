"""Backup manifest and backup-before-write (SPEC.md 5).

Nothing wrsrcli touches is ever hard-deleted. A `remove` moves the file
into the backup store; a `copy` that would overwrite an existing file
copies that file into the store first. Both are logged before the
destructive step, so an interrupted run leaves a manifest entry pointing
at a real backup rather than a lost file.

Layout (decision D-009):

    %APPDATA%\\wrsrcli\\backups.json
    %APPDATA%\\wrsrcli\\backups\\{origin}\\{YYYYMMDD-HHMMSS}\\{nnn}_{name}

One timestamped folder per `import` run — one run is one generation.
"""

import datetime
import json
import shutil

from . import config
from .errors import WrsrcliError

VANILLA = "vanilla"

COPY = "copy"
REMOVE = "remove"


def manifest_path():
    return config.config_dir() / "backups.json"


def store_root():
    return config.config_dir() / "backups"


def load():
    """Every backup entry ever recorded, oldest first."""
    path = manifest_path()
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
    path = manifest_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise WrsrcliError(f"could not write {path}: {exc}") from exc


class Run:
    """One `import` execution — one backup generation.

    The run folder is created lazily, so an import that overwrites nothing
    leaves no empty directory behind.
    """

    def __init__(self, origin_steamid, stamp=None):
        self.origin_steamid = str(origin_steamid)
        self.stamp = stamp or self._free_stamp()
        self.entries = []
        self._counter = 0

    def _free_stamp(self):
        """A run stamp not already used by this origin.

        The stamp has one-second resolution, so two imports of the same
        origin inside the same second would otherwise share a folder *and*
        restart the file counter — overwriting the earlier run's backups.
        """
        base = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        parent = store_root() / self.origin_steamid
        if not (parent / base).exists():
            return base
        suffix = 2
        while (parent / f"{base}-{suffix}").exists():
            suffix += 1
        return f"{base}-{suffix}"

    @property
    def folder(self):
        return store_root() / self.origin_steamid / self.stamp

    def _next_backup_path(self, original):
        self._counter += 1
        return self.folder / f"{self._counter:03d}_{original.name}"

    def _record(self, destination, action, original, backup):
        entry = {
            "origin_steamid": self.origin_steamid,
            "destination": destination,
            "action": action,
            "original_path": str(original),
            "backup_path": str(backup),
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self.entries.append(entry)
        return entry

    def stash_overwrite(self, destination, original):
        """Back up a file that is about to be overwritten by `copy`."""
        backup = self._next_backup_path(original)
        try:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, backup)
        except OSError as exc:
            raise WrsrcliError(
                f"could not back up {original} before overwriting it: {exc}"
            ) from exc
        return self._record(destination, COPY, original, backup)

    def stash_removal(self, destination, original):
        """Move a file or directory out of the way for `remove`."""
        backup = self._next_backup_path(original)
        try:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(original), str(backup))
        except OSError as exc:
            raise WrsrcliError(f"could not move {original} to backup: {exc}") from exc
        return self._record(destination, REMOVE, original, backup)

    def commit(self):
        """Append this run's entries to the manifest."""
        if not self.entries:
            return 0
        existing = load()
        existing.extend(self.entries)
        save(existing)
        return len(self.entries)


def generations(entries):
    """Group entries into generations, keyed by (origin_steamid, stamp).

    The stamp is taken from the backup path's run folder, which is what
    actually groups one `import` execution.
    """
    grouped = {}
    for entry in entries:
        origin = entry.get("origin_steamid", "")
        stamp = _stamp_of(entry)
        grouped.setdefault((origin, stamp), []).append(entry)
    return grouped


def _stamp_of(entry):
    """The run stamp for an entry, from its backup path's parent folder."""
    from pathlib import PurePath

    parent = PurePath(entry.get("backup_path", "")).parent.name
    return parent or entry.get("timestamp", "")


def describe(stamp):
    """Render a run stamp as a readable date, falling back to the raw value.

    Same-second runs carry a `-2`, `-3`, ... suffix; strip it before
    parsing so those generations still display as a date.
    """
    text = stamp or ""
    head, _, tail = text.rpartition("-")
    if head and tail.isdigit() and len(tail) < 6:
        text = head

    try:
        moment = datetime.datetime.strptime(text, "%Y%m%d-%H%M%S")
    except (TypeError, ValueError):
        return stamp
    return moment.strftime("%Y-%m-%d %H:%M")

"""`wrsrcli manual-check` — spotting imports Steam has quietly reverted.

SPEC.md 4.7. Steam can silently replace manually-placed files when a
workshop item or the game is updated or verified. There is no event to
listen for, so this compares each backup entry against the current state:

- destination is a workshop item: that item's `.acf` `timeupdated` versus
  the entry's timestamp.
- destination is `[GAME]/...` ("vanilla"): the file's own filesystem mtime
  versus the entry's timestamp. This can false-positive, since anything
  touching the mtime trips it. Accepted for v1, per 4.7.
"""

import datetime
from pathlib import Path

from .backup import VANILLA


def _entry_time(entry):
    try:
        return datetime.datetime.fromisoformat(entry.get("timestamp", ""))
    except (TypeError, ValueError):
        return None


def _newest_per_path(entries):
    """The most recent backup entry for each original path (SPEC.md 4.7)."""
    newest = {}
    for entry in entries:
        path = entry.get("original_path")
        if not path:
            continue
        current = newest.get(path)
        if current is None or entry.get("timestamp", "") >= current.get("timestamp", ""):
            newest[path] = entry
    return newest


def check(entries, acf_items):
    """Flag entries whose destination looks touched since the backup.

    `acf_items` is {item_id: WorkshopItem} from acf.parse. Returns a list
    of (entry, reason) pairs, newest-relevant entry per path only.
    """
    flagged = []

    for path, entry in sorted(_newest_per_path(entries).items()):
        backed_up_at = _entry_time(entry)
        if backed_up_at is None:
            continue

        destination = entry.get("destination")

        if destination and destination != VANILLA:
            item = acf_items.get(destination)
            if item is None or not item.timeupdated:
                continue
            try:
                updated = datetime.datetime.fromtimestamp(int(item.timeupdated))
            except (TypeError, ValueError, OSError, OverflowError):
                continue
            if updated > backed_up_at:
                flagged.append(
                    (
                        entry,
                        f"workshop item {destination} was updated "
                        f"{updated:%Y-%m-%d %H:%M}, after this import",
                    )
                )
            continue

        # Game file: no .acf applies, so fall back to the filesystem mtime.
        target = Path(path)
        if not target.exists():
            flagged.append((entry, "the file is missing"))
            continue
        try:
            raw_mtime = target.stat().st_mtime
        except OSError:
            continue
        modified = datetime.datetime.fromtimestamp(raw_mtime)

        # Compare against the mtime the file had once the import placed it.
        # shutil.copy2 carries the source's mtime across, so the backup's own
        # timestamp is not a usable baseline — it would flag every import as
        # soon as it finished. Older entries without the field fall back to it.
        placed = entry.get("placed_mtime")
        if placed is not None:
            if raw_mtime > placed:
                flagged.append(
                    (entry, f"modified {modified:%Y-%m-%d %H:%M}, after this import")
                )
            continue

        if modified > backed_up_at:
            flagged.append(
                (entry, f"modified {modified:%Y-%m-%d %H:%M}, after this import")
            )

    return flagged

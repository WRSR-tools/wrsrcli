"""What needs fetching: unmet dependencies and out-of-date items (D-021).

Shared by `output-table`, which reports both in its status accordions, and
`update`, which acts on them. Keeping the two in one place is what stops
the table saying one thing and the command doing another.
"""

from . import steamworks


def unmet(entries):
    """Dependencies referenced by an installed item but not installed.

    One entry per missing item, in id order, carrying the name and creator
    the scan recorded plus the ids of the items that need it.
    """
    installed = {e.get("item_id") for e in entries if e.get("item_id")}
    missing = {}

    for entry in entries:
        for dep in entry.get("dependencies") or []:
            item_id = dep.get("item_id")
            if not item_id or item_id in installed:
                continue
            found = missing.setdefault(
                item_id,
                {
                    "item_id": item_id,
                    "name": dep.get("name") or "",
                    "creator": dep.get("creator") or dep.get("creator_id") or "",
                    "creator_id": dep.get("creator_id") or "",
                    "required_by": [],
                },
            )
            if entry.get("item_id"):
                found["required_by"].append(entry["item_id"])

    return [missing[key] for key in sorted(missing)]


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def outdated(entries, handle=None):
    """Installed items with a newer version published.

    Two sources (decision D-024):

    - a connected Steamworks handle, where `GetItemState` reports
      `NeedsUpdate` — Steam's own live answer, no timestamps involved;
    - otherwise the `.acf`'s `latest_timeupdated`, captured by `scan` as
      `date_latest`, which keeps the check working with Steam closed.

    An item is out of date only on positive evidence. A missing or
    unreadable value is never read as "update it", so neither a closed Steam
    client nor an .acf without the field can invent work.
    """
    stale = []

    for entry in entries:
        item_id = entry.get("item_id")
        if not item_id:
            continue

        if handle is not None:
            bits = handle.state(item_id)
            # An item still downloading is already being dealt with.
            if bits & steamworks.NEEDS_UPDATE and not bits & (
                steamworks.DOWNLOADING | steamworks.DOWNLOAD_PENDING
            ):
                stale.append({
                    "item_id": item_id,
                    "name": entry.get("title") or "",
                    "source": "steam",
                })
            continue

        local = _as_int(entry.get("date_updated"))
        remote = _as_int(entry.get("date_latest"))
        if local is None or remote is None or remote <= local:
            continue
        stale.append({
            "item_id": item_id,
            "name": entry.get("title") or "",
            "local": local,
            "remote": remote,
            "source": "acf",
        })

    return stale


def can_check_staleness(entries):
    """Whether anything on disk can say if an item is out of date.

    Needs an .acf that carried `latest_timeupdated` into the manifest. With
    nothing to check against, the Asset status panel is absent rather than
    claiming everything is current (D-022, D-024).
    """
    return any(entry.get("date_latest") for entry in entries)

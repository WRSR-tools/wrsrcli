"""What needs fetching: unmet dependencies and out-of-date items (D-021).

Shared by `output-table`, which reports both in its status accordions, and
`update`, which acts on them. Keeping the two in one place is what stops
the table saying one thing and the command doing another.
"""


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


def outdated(entries, details=None):
    """Installed items whose published version is newer than the local one.

    Two sources, in order of authority (decision D-022):

    - the Steam Web API's `time_updated`, which is live, when `details`
      carries the item;
    - otherwise the `.acf`'s own `latest_timeupdated`, which Steam maintains
      as of its last check. This is what makes the check work with no key
      and no network.

    An item is out of date only when both timestamps are readable and the
    published one is strictly greater. A missing or unparseable value means
    "no evidence of an update", never "update it", so neither a partial API
    response nor an .acf without the field can invent work.
    """
    details = details or {}
    stale = []

    for entry in entries:
        item_id = entry.get("item_id")
        if not item_id:
            continue

        local = _as_int(entry.get("date_updated"))
        remote = _as_int((details.get(item_id) or {}).get("time_updated"))
        source = "api"
        if remote is None:
            remote = _as_int(entry.get("date_latest"))
            source = "acf"

        if local is None or remote is None or remote <= local:
            continue

        stale.append(
            {
                "item_id": item_id,
                "local": local,
                "remote": remote,
                "source": source,
            }
        )

    return stale


def can_check_staleness(entries, api_mode=False):
    """Whether anything can say if an item is out of date.

    With a key the API answers for every item; without one it takes an .acf
    that carried `latest_timeupdated`. Neither means the Asset status panel
    is absent rather than claiming everything is current (D-022).
    """
    return bool(api_mode) or any(entry.get("date_latest") for entry in entries)

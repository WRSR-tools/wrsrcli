"""`wrsrcli scan` — build manifest.json from the .acf and workshop folder.

SPEC.md 4.1. One entry per *installed* item; items the .acf lists only
under WorkshopItemDetails are subscribed-but-not-downloaded and are not
inventoried.

The inventory itself is local. Dependencies are the one field that is not:
they exist only in the Steam Web API, behind a key, so they are attached
afterwards and a failure to fetch them leaves the manifest otherwise
complete (decision D-020).
"""

import json

from . import acf, config, steam, steamapi, workshopconfig
from .errors import WrsrcliError

OWNER_ID = "$OWNER_ID"
ITEM_TYPE = "$ITEM_TYPE"


def build(workshop_path, acf_path):
    """Return (entries, warnings) for every installed item."""
    items = acf.parse(acf_path)

    entries = []
    warnings = []

    for item_id in sorted(items):
        item = items[item_id]
        if not item.installed:
            continue

        owner_id = None
        item_type = None

        config_file = workshop_path / item_id / "workshopconfig.ini"
        if config_file.exists():
            record = workshopconfig.load(config_file)
            owner_id = workshopconfig.first(record, OWNER_ID)
            item_type = workshopconfig.first(record, ITEM_TYPE)
        else:
            # Ships with every workshop download, so its absence means it was
            # deleted locally. Report it and keep the entry (decision D-005).
            warnings.append(
                f"{item_id} has no workshopconfig.ini (listed as installed in "
                "the .acf) — owner_id and item_type left null"
            )

        entries.append(
            {
                "item_id": item_id,
                "owner_id": owner_id,
                "item_type": item_type,
                "date_updated": item.timeupdated,
                "date_touched": item.timetouched,
            }
        )

    return entries, warnings


def add_dependencies(entries, key):
    """Attach Steam's declared required items to each entry, in place.

    Sets `dependencies` on every entry — an empty list where the item
    declares none — so a manifest that went through this step is
    distinguishable from one written without a key, which has no such key
    at all. Whether a dependency is *installed* is deliberately not stored;
    it is derived from the manifest's own entries at render time (D-020).

    Returns the number of dependency-declaring items and the set of
    unmet dependency ids.
    """
    item_ids = [entry["item_id"] for entry in entries if entry.get("item_id")]
    children = steamapi.published_file_children(key, item_ids)

    referenced = sorted({cid for listed in children.values() for cid in listed})
    # The dependency's own metadata: an unmet one has no folder on disk, so
    # the API is the only place its name and creator can come from.
    meta = steamapi.published_file_details(referenced) if referenced else {}
    creators = sorted(
        {m["creator"] for m in meta.values() if m.get("creator")}
    )
    names = steamapi.player_names(key, creators) if creators else {}

    installed = set(item_ids)
    for entry in entries:
        listed = children.get(entry.get("item_id"), [])
        entry["dependencies"] = [
            {
                "item_id": cid,
                "name": (meta.get(cid) or {}).get("title") or "",
                "creator_id": (meta.get(cid) or {}).get("creator") or "",
                "creator": names.get((meta.get(cid) or {}).get("creator") or "", ""),
            }
            for cid in listed
        ]

    unmet = {cid for cid in referenced if cid not in installed}
    return len(children), unmet


def write_manifest(entries):
    path = config.manifest_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise WrsrcliError(f"could not write {path}: {exc}") from exc
    return path

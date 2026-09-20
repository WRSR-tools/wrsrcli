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

from . import acf, config, steam, steamworks, workshopconfig
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
                # Steam's own note of the newest version it knows of, which
                # makes staleness answerable without the API (D-022).
                "date_latest": item.latest_timeupdated,
            }
        )

    entries.extend(_folder_only(workshop_path, set(items), warnings))
    entries.sort(key=lambda entry: entry["item_id"])
    return entries, warnings


def _folder_only(workshop_path, known, warnings):
    """Installed items the .acf does not mention.

    Since D-024 nothing wrsrcli does places files outside Steam, so a folder
    Steam has no record of was put there by something else. It is still
    inventoried — it is on disk and the game will load it — but it is always
    warned about, and Steam will neither update it nor know it exists.
    """
    if not workshop_path.is_dir():
        return []

    extra = []
    for folder in sorted(workshop_path.iterdir()):
        if not folder.is_dir() or not folder.name.isdigit() or folder.name in known:
            continue

        owner_id = item_type = None
        config_file = folder / "workshopconfig.ini"
        if config_file.exists():
            record = workshopconfig.load(config_file)
            owner_id = workshopconfig.first(record, OWNER_ID)
            item_type = workshopconfig.first(record, ITEM_TYPE)

        warnings.append(
            f"{folder.name} is on disk but Steam has no record of it — it was "
            "not installed through Steam, so it will never be updated. "
            "Subscribe to it to put that right."
        )
        extra.append(
            {
                "item_id": folder.name,
                "owner_id": owner_id,
                "item_type": item_type,
                "date_updated": None,
                "date_touched": None,
            }
        )

    return extra


def add_dependencies(entries, handle):
    """Attach Steam's declared required items to each entry, in place.

    `handle` is a connected `steamworks.Steamworks`. Sets `dependencies` on
    every entry — empty where an item declares none — so a manifest built
    with Steam running is distinguishable from one built without it, which
    has no such key at all.

    Whether a dependency is *installed* is deliberately not stored; it is
    derived from the manifest's own entries at render time (D-020).

    Returns the number of dependency-declaring items and the set of unmet
    dependency ids.
    """
    item_ids = [entry["item_id"] for entry in entries if entry.get("item_id")]
    published = handle.details(item_ids)

    referenced = sorted({
        child
        for record in published.values()
        for child in record["children"]
    })
    # A dependency need not be installed, so its own record is fetched too:
    # nothing on disk can name it.
    if referenced:
        published.update(handle.details([i for i in referenced if i not in published]))

    # Every owner in play, so the table can name authors with Steam closed.
    names = handle.persona_names({
        record["owner_id"] for record in published.values() if record.get("owner_id")
    })

    installed = set(item_ids)
    declaring = 0
    for entry in entries:
        record = published.get(entry.get("item_id"))
        children = record["children"] if record else []
        if children:
            declaring += 1
        entry["dependencies"] = [
            {
                "item_id": child,
                "name": (published.get(child) or {}).get("title") or "",
                "creator_id": (published.get(child) or {}).get("owner_id") or "",
                "creator": names.get(
                    (published.get(child) or {}).get("owner_id") or "", ""
                ),
            }
            for child in children
        ]
        # Steam's own metadata also fills in what the local files cannot.
        if record:
            entry["title"] = record["title"]
            entry["date_published"] = record["created"]
            if not entry.get("owner_id"):
                entry["owner_id"] = record["owner_id"]
            entry["author"] = names.get(entry.get("owner_id") or "", "")
        # Size comes from the client's own install record rather than the
        # published metadata: it is what is actually on this disk, and it
        # needs no struct offsets to read.
        info = handle.install_info(entry.get("item_id"))
        if info:
            entry["size_on_disk"] = str(info[0])

    unmet = {child for child in referenced if child not in installed}
    return declaring, unmet


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

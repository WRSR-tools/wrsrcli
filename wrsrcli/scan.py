"""`wrsrcli scan` — build manifest.json from the .acf and workshop folder.

SPEC.md 4.1. One entry per *installed* item; items the .acf lists only
under WorkshopItemDetails are subscribed-but-not-downloaded and are not
inventoried.
"""

import json

from . import acf, config, steam, workshopconfig
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

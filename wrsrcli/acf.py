"""Reading `appworkshop_{appid}.acf` — the installed/subscribed item list.

SPEC.md 2.1: two blocks cover the same item IDs. `WorkshopItemsInstalled`
carries `size`, `timeupdated`, `manifest`; `WorkshopItemDetails` carries
`timeupdated`, `timetouched`, `subscribedby`, `manifest` but no `size`. An
item in details but not in installed is subscribed-but-not-downloaded.

Details also carries `latest_timeupdated`/`latest_manifest` — Steam's own
record of the newest version it knows about, as of `TimeLastFullCheck`.
That makes staleness answerable locally, without the Web API (D-022).
"""

from . import vdf
from .errors import WrsrcliError


class WorkshopItem:
    """One workshop item as described by the .acf."""

    __slots__ = (
        "item_id",
        "installed",
        "size",
        "timeupdated",
        "timetouched",
        "subscribedby",
        "manifest",
        "latest_timeupdated",
        "latest_manifest",
    )

    def __init__(self, item_id):
        self.item_id = item_id
        self.installed = False
        self.size = None
        self.timeupdated = None
        self.timetouched = None
        self.subscribedby = None
        self.manifest = None
        self.latest_timeupdated = None
        self.latest_manifest = None

    def __repr__(self):
        state = "installed" if self.installed else "subscribed-only"
        return f"<WorkshopItem {self.item_id} {state}>"


def parse(path):
    """Parse an appworkshop .acf into {item_id: WorkshopItem}, by item ID."""
    root = vdf.lookup(vdf.load(path), "AppWorkshop")
    if root is None:
        raise WrsrcliError(f"{path} has no 'AppWorkshop' block.")

    installed_block = vdf.lookup(root, "WorkshopItemsInstalled") or {}
    details_block = vdf.lookup(root, "WorkshopItemDetails") or {}

    items = {}

    for item_id, fields in installed_block.items():
        if not isinstance(fields, dict):
            continue
        item = items.setdefault(item_id, WorkshopItem(item_id))
        item.installed = True
        item.size = vdf.lookup(fields, "size")
        item.timeupdated = vdf.lookup(fields, "timeupdated")
        item.manifest = vdf.lookup(fields, "manifest")

    for item_id, fields in details_block.items():
        if not isinstance(fields, dict):
            continue
        item = items.setdefault(item_id, WorkshopItem(item_id))
        item.timetouched = vdf.lookup(fields, "timetouched")
        item.subscribedby = vdf.lookup(fields, "subscribedby")
        # Steam's view of the newest published version, refreshed on its own
        # schedule. Compared against timeupdated, this is staleness with no
        # API call (decision D-022).
        item.latest_timeupdated = vdf.lookup(fields, "latest_timeupdated")
        item.latest_manifest = vdf.lookup(fields, "latest_manifest")
        # Details also carries timeupdated/manifest; installed wins where both
        # are present, since that block describes what is actually on disk.
        if item.timeupdated is None:
            item.timeupdated = vdf.lookup(fields, "timeupdated")
        if item.manifest is None:
            item.manifest = vdf.lookup(fields, "manifest")

    return items

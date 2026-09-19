"""Parsing and resolving YAML import lists (SPEC.md 4.3).

An import list names an origin workshop item and the `copy`/`remove`
operations to apply for it. Destination paths use `[GAME]` and
`[WORKSHOP]/{id}/` placeholders, resolved against the configured game path
and the target item's own workshop folder.
"""

import re

import yaml

from .backup import VANILLA
from .errors import WrsrcliError

GAME = "[GAME]"
WORKSHOP = "[WORKSHOP]"

EVERYTHING = "*"
EXCLUDED_FROM_STAR = "workshopconfig.ini"

_WORKSHOP_DST = re.compile(r"^\[WORKSHOP\]/(\d+)/?(.*)$")


class ImportList:
    def __init__(self, item, copies, removals, source):
        self.item = item
        self.copies = copies
        self.removals = removals
        self.source = source


def load(path):
    """Parse an import list. Raises WrsrcliError on anything malformed."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WrsrcliError(f"could not read {path}: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise WrsrcliError(f"{path} is not valid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise WrsrcliError(f"{path} should contain a YAML mapping.")

    item = data.get("item")
    if item is None:
        raise WrsrcliError(f"{path} has no `item:` — the origin workshop item ID.")
    item = str(item).strip()
    if not item.isdigit():
        raise WrsrcliError(f"{path}: `item:` should be a numeric workshop ID, got {item!r}.")

    copies = _parse_copies(data.get("copy") or [], path)
    removals = _parse_removals(data.get("remove") or [], path)

    if not copies and not removals:
        raise WrsrcliError(f"{path} has no `copy:` or `remove:` operations.")

    return ImportList(item, copies, removals, path)


def _parse_copies(raw, path):
    if not isinstance(raw, list):
        raise WrsrcliError(f"{path}: `copy:` should be a list of src/dst pairs.")

    copies = []
    for index, pair in enumerate(raw, 1):
        if not isinstance(pair, dict):
            raise WrsrcliError(f"{path}: copy entry {index} should be a mapping.")
        src = pair.get("src")
        dst = pair.get("dst")
        if not src or not dst:
            raise WrsrcliError(f"{path}: copy entry {index} needs both `src` and `dst`.")
        copies.append((str(src).strip(), str(dst).strip()))
    return copies


def _parse_removals(raw, path):
    if not isinstance(raw, list):
        raise WrsrcliError(f"{path}: `remove:` should be a list of paths.")

    removals = []
    for index, target in enumerate(raw, 1):
        if not isinstance(target, str) or not target.strip():
            raise WrsrcliError(f"{path}: remove entry {index} should be a path string.")
        removals.append(target.strip())
    return removals


def resolve_destination(raw, game_path, workshop_root):
    """Resolve a `[GAME]`/`[WORKSHOP]` destination.

    Returns (path, destination_id) where destination_id is the workshop
    item whose files are affected, or "vanilla" for base game files.
    """
    text = raw.replace("\\", "/")

    match = _WORKSHOP_DST.match(text)
    if match:
        item_id, remainder = match.groups()
        base = workshop_root / item_id
        return (base / remainder if remainder else base), item_id

    if text.startswith(GAME):
        remainder = text[len(GAME) :].lstrip("/")
        return (game_path / remainder if remainder else game_path), VANILLA

    raise WrsrcliError(
        f"destination {raw!r} must start with `{GAME}` or `{WORKSHOP}/{{id}}/`."
    )


def expand_source(src, origin_folder):
    """Resolve a `src` to concrete (file, relative_path) pairs.

    `*` means everything in the origin folder except workshopconfig.ini
    (SPEC.md 4.3 — the exclusion is fixed). A trailing `/` or a directory
    copies the tree; a plain filename copies one file.
    """
    if src == EVERYTHING:
        results = []
        for entry in sorted(origin_folder.rglob("*")):
            if entry.is_file() and entry.name != EXCLUDED_FROM_STAR:
                results.append((entry, entry.relative_to(origin_folder)))
        if not results:
            raise WrsrcliError(f"{origin_folder} has nothing to copy for `src: \"*\"`.")
        return results

    target = (origin_folder / src.replace("\\", "/").rstrip("/")).resolve()

    # Keep the copy confined to the origin item's own folder.
    try:
        target.relative_to(origin_folder.resolve())
    except ValueError:
        raise WrsrcliError(
            f"src {src!r} resolves outside the origin item's folder."
        ) from None

    if not target.exists():
        raise WrsrcliError(f"src {src!r} not found in {origin_folder}.")

    if target.is_dir():
        results = [
            (entry, entry.relative_to(target.parent))
            for entry in sorted(target.rglob("*"))
            if entry.is_file()
        ]
        if not results:
            raise WrsrcliError(f"src {src!r} is an empty directory.")
        return results

    return [(target, target.name)]

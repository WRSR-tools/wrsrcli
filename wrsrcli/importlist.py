"""Parsing and resolving YAML import lists (SPEC.md 4.3, WMLS v1).

An import list names one or more origin workshop items and, for each, the
`copy`/`remove` operations to apply and the items it depends on.
Destination paths use `[GAME]` and `[WORKSHOP]/{id}/` placeholders,
resolved against the configured game path and the target item's own
workshop folder.

Two markup versions are accepted (decision D-018):

- `version: 1` — items live in an `items:` list, and each may declare
  `depends-mandatory:`/`depends-optional:`.
- no `version:` key — the `beta` markup, a single top-level `item:` with
  its own `copy:`/`remove:`. Still parsed, with a deprecation warning.
"""

import re
import sys

import yaml

from .backup import VANILLA
from .errors import WrsrcliError

GAME = "[GAME]"
WORKSHOP = "[WORKSHOP]"

EVERYTHING = "*"
EXCLUDED_FROM_STAR = "workshopconfig.ini"

BETA = "beta"
V1 = 1

_WORKSHOP_DST = re.compile(r"^\[WORKSHOP\]/(\d+)/?(.*)$")

BETA_WARNING = (
    "warning: {path} uses the `beta` markup (no `version:` line). Support for "
    "it will be dropped — add `version: 1` and move the item under `items:`."
)


class Dependency:
    """One `depends-mandatory:`/`depends-optional:` entry."""

    __slots__ = ("item", "message")

    def __init__(self, item, message=None):
        self.item = item
        self.message = message


class Item:
    """One origin item and everything the list asks for on its behalf."""

    __slots__ = ("item", "copies", "removals", "mandatory", "optional")

    def __init__(self, item, copies, removals, mandatory, optional):
        self.item = item
        self.copies = copies
        self.removals = removals
        self.mandatory = mandatory
        self.optional = optional


class ImportList:
    def __init__(self, version, items, source):
        self.version = version
        self.items = items
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

    version = data.get("version")
    if version is None:
        print(BETA_WARNING.format(path=path), file=sys.stderr)
        return ImportList(BETA, [_parse_beta(data, path)], path)

    if version != V1:
        raise WrsrcliError(
            f"{path}: `version: {version}` is not a markup version wrsrcli "
            f"knows. This build understands `version: 1`."
        )

    return ImportList(V1, _parse_v1(data, path), path)


def _parse_beta(data, path):
    """The single-item markup: `item:` at the top level, no dependencies."""
    if "items" in data:
        raise WrsrcliError(
            f"{path} has an `items:` list but no `version:` line — add "
            f"`version: 1` as the first line."
        )

    return _parse_item(data, path, f"{path}")


def _parse_v1(data, path):
    raw = data.get("items")
    if raw is None:
        if "item" in data:
            raise WrsrcliError(
                f"{path}: `version: 1` puts every item under an `items:` list, "
                f"even when there is only one."
            )
        raise WrsrcliError(f"{path} has no `items:` list.")

    if not isinstance(raw, list) or not raw:
        raise WrsrcliError(f"{path}: `items:` should be a non-empty list of items.")

    items = []
    seen = set()
    for index, entry in enumerate(raw, 1):
        if not isinstance(entry, dict):
            raise WrsrcliError(f"{path}: item {index} should be a mapping.")
        parsed = _parse_item(entry, path, f"{path}: item {index}")
        # Two entries for one origin would each open their own backup
        # generation for the same item — the second silently masking the
        # first in `manual-rerun`'s latest-per-origin view.
        if parsed.item in seen:
            raise WrsrcliError(
                f"{path}: item {parsed.item} is listed more than once — "
                f"merge its `copy:`/`remove:` entries into one item."
            )
        seen.add(parsed.item)
        items.append(parsed)
    return items


def _parse_item(data, path, label):
    item = data.get("item")
    if item is None:
        raise WrsrcliError(f"{label} has no `item:` — the origin workshop item ID.")
    item = str(item).strip()
    if not item.isdigit():
        raise WrsrcliError(
            f"{label}: `item:` should be a numeric workshop ID, got {item!r}."
        )

    copies = _parse_copies(data.get("copy") or [], label)
    removals = _parse_removals(data.get("remove") or [], label)
    mandatory = _parse_dependencies(data, "depends-mandatory", label, False)
    optional = _parse_dependencies(data, "depends-optional", label, True)

    if not copies and not removals and not mandatory and not optional:
        raise WrsrcliError(f"{label} has nothing to do — no `copy:`, `remove:` or dependencies.")

    return Item(item, copies, removals, mandatory, optional)


def _parse_copies(raw, label):
    if not isinstance(raw, list):
        raise WrsrcliError(f"{label}: `copy:` should be a list of src/dst pairs.")

    copies = []
    for index, pair in enumerate(raw, 1):
        if not isinstance(pair, dict):
            raise WrsrcliError(f"{label}: copy entry {index} should be a mapping.")
        src = pair.get("src")
        dst = pair.get("dst")
        if not src or not dst:
            raise WrsrcliError(f"{label}: copy entry {index} needs both `src` and `dst`.")
        src = str(src).strip()
        # `*` is the whole origin folder, not a glob — `signs/*` would read
        # as a wildcard it isn't, so reject it rather than quietly treating
        # it as a literal path that will never exist.
        if EVERYTHING in src and src != EVERYTHING:
            raise WrsrcliError(
                f"{label}: copy entry {index} has src {src!r}. `*` means the whole "
                f"origin folder and cannot appear inside a path — use a trailing "
                f"`/` to copy a folder's contents."
            )
        copies.append((src, str(dst).strip()))
    return copies


def _parse_removals(raw, label):
    if not isinstance(raw, list):
        raise WrsrcliError(f"{label}: `remove:` should be a list of paths.")

    removals = []
    for index, target in enumerate(raw, 1):
        if not isinstance(target, str) or not target.strip():
            raise WrsrcliError(f"{label}: remove entry {index} should be a path string.")
        removals.append(target.strip())
    return removals


def _parse_dependencies(data, key, label, wants_message):
    raw = data.get(key)
    if raw is None:
        # The beta document advertised underscored spellings for these; WMLS
        # v1 settled on hyphens. Name the right key rather than ignoring the
        # wrong one, which would silently drop the dependency.
        legacy = key.replace("-", "_")
        if legacy in data:
            raise WrsrcliError(f"{label}: `{legacy}:` is spelled `{key}:` in WMLS v1.")
        return []

    if not isinstance(raw, list):
        raise WrsrcliError(f"{label}: `{key}:` should be a list of items.")

    dependencies = []
    seen = set()
    for index, entry in enumerate(raw, 1):
        if not isinstance(entry, dict):
            raise WrsrcliError(f"{label}: {key} entry {index} should be a mapping.")
        item = entry.get("item")
        if item is None:
            raise WrsrcliError(f"{label}: {key} entry {index} needs an `item:`.")
        item = str(item).strip()
        if not item.isdigit():
            raise WrsrcliError(
                f"{label}: {key} entry {index} should be a numeric workshop ID, "
                f"got {item!r}."
            )
        if item in seen:
            continue
        seen.add(item)

        message = entry.get("message")
        if message is not None:
            message = str(message).strip()
        if wants_message and not message:
            raise WrsrcliError(
                f"{label}: {key} entry {index} needs a `message:` explaining what "
                f"item {item} adds — it is what the user is asked about."
            )
        dependencies.append(Dependency(item, message))
    return dependencies


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

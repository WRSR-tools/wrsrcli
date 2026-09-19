"""Executing an import list (SPEC.md 4.3).

Order of operations matters here. Everything is planned and every conflict
is settled *before* the first file is written, so a run either proceeds
with the user's decisions already made or stops having changed nothing.
Once writing starts, each destructive step is preceded by its backup.
"""

import datetime
import shutil

from . import importlist
from .errors import WrsrcliError


class Planned:
    """One resolved copy: source file -> destination file."""

    __slots__ = ("source", "destination", "destination_id")

    def __init__(self, source, destination, destination_id):
        self.source = source
        self.destination = destination
        self.destination_id = destination_id


def plan_copies(entries, origin_folder, game_path, workshop_root):
    """Expand every copy entry into concrete destinations.

    Returns (planned, conflicts) where `conflicts` maps a destination path
    to the competing source files, in entry order (decision D-010).
    """
    by_destination = {}

    for src, dst in entries:
        base, destination_id = importlist.resolve_destination(
            dst, game_path, workshop_root
        )
        for source, relative in importlist.expand_source(src, origin_folder):
            destination = base / relative
            slot = by_destination.setdefault(destination, [])
            # Same source twice for one destination is a duplicate, not a
            # conflict — drop it silently.
            if not any(existing.source == source for existing in slot):
                slot.append(Planned(source, destination, destination_id))

    planned = []
    conflicts = {}
    for destination, candidates in by_destination.items():
        if len(candidates) == 1:
            planned.append(candidates[0])
        else:
            conflicts[destination] = candidates

    return planned, conflicts


def describe_mtime(path):
    try:
        moment = datetime.datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return "unknown"
    return moment.strftime("%Y-%m-%d %H:%M")


def execute_copies(planned, run):
    """Copy each planned file, backing up anything it overwrites."""
    written = 0
    for item in planned:
        try:
            item.destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WrsrcliError(
                f"could not create {item.destination.parent}: {exc}"
            ) from exc

        # Back up before overwriting — never the other way round (SPEC.md 5).
        entry = None
        if item.destination.exists():
            entry = run.stash_overwrite(item.destination_id, item.destination)

        try:
            shutil.copy2(item.source, item.destination)
        except OSError as exc:
            raise WrsrcliError(
                f"could not copy {item.source} to {item.destination}: {exc}"
            ) from exc

        # Record the mtime this file has now that we placed it. copy2 carries
        # the *source's* mtime across, so "now" is the wrong baseline and the
        # backup's own timestamp would make manual-check flag every import the
        # moment it finished. This is the value 4.7's staleness check compares
        # against later.
        if entry is not None:
            try:
                entry["placed_mtime"] = item.destination.stat().st_mtime
            except OSError:
                pass

        written += 1

    return written


def execute_removals(targets, game_path, workshop_root, run):
    """Move each removal target into the backup store. Never deletes.

    Returns (removed, missing) — `missing` names targets that were already
    absent, which is reported but is not an error.
    """
    removed = 0
    missing = []

    for raw in targets:
        path, destination_id = importlist.resolve_destination(
            raw, game_path, workshop_root
        )
        if not path.exists():
            missing.append(raw)
            continue
        run.stash_removal(destination_id, path)
        removed += 1

    return removed, missing

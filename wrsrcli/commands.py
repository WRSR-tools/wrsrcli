"""Implementations for the wrsrcli subcommands."""

import ctypes
import ctypes.wintypes as wintypes
import datetime
import os
import shutil
import sys
import webbrowser
from pathlib import Path

from . import APP_ID, acf, backup, config, history, importer, importlist
from . import install, scan, staleness, steam, steamapi, steamcmd, table
from .errors import WrsrcliError

# Verbatim per SPEC.md 4.2 — do not reword.
NO_API_KEY_MESSAGE = """Steam Web API key has not been set. To retrieve metadata from Steam, please obtain an API key from:
   https://steamcommunity.com/dev/apikey

wrsrcli will now build an HTML table of your assets using workshopconfig.ini."""

SAVE_PROMPT = (
    "Please enter path to save folder, or press ENTER to use Documents. "
    "The filename will be WRSR Assets.html: "
)

COLLISION_PROMPT = """WRSR Assets.html found. Do you want to:
   1. Overwrite the current file
   2. Append a timestamp to the new file

Please select: """

OUTPUT_NAME = "WRSR Assets.html"

# Verbatim per SPEC.md 3 — do not reword.
STEAMCMD_PROMPT = """Press ENTER to automatically download and install steamcmd from Valve. If you prefer to download and install yourself, please open this link:
   https://developer.valvesoftware.com/wiki/SteamCMD
"""

# Verbatim per SPEC.md 3 — do not reword. The title line is shown in rust, and
# in the prompt only the key name is; everything else is plain (D-016, D-017).
FIRST_RUN_TITLE = (
    "wrsrcli dev - Workshop Manager for Workers and Resources: Soviet Republic"
)
FIRST_RUN_BODY = """\
================================================================================
This is the installer for the wrsrcli - a command line tool to manage workshop
assets for Workers and Resources: Soviet Republic.

For more information on how to use this tool, please visit:
   https://wrsr-tools.github.io
"""
# Split so that only the key name is coloured, per SPEC.md 3.
FIRST_RUN_PROMPT_BEFORE = "   Press "
FIRST_RUN_PROMPT_KEY = "ENTER"
FIRST_RUN_PROMPT_AFTER = " to install..."

# The site `open-web` opens, and the one the first-run screen points at.
WEBSITE = "https://wrsr-tools.github.io/"

# Rusty red, matching the game's palette and `output-table`'s own accent.
# Written as a 24-bit colour: Windows Terminal reproduces it exactly, and
# legacy conhost maps it to the nearest entry in its palette.
RUST = "\x1b[38;2;183;65;14m"
RESET = "\x1b[0m"

_STD_OUTPUT_HANDLE = -11
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004


def enable_ansi():
    """Turn on ANSI escape handling for this console. True if colour is usable.

    Windows Terminal handles escapes out of the box, but legacy `conhost`
    ignores them unless VT processing is switched on for the handle — and a
    console that ignores them prints the raw `←[38;2;...m` instead, which is
    worse than no colour at all. So colour is used only once this has
    actually succeeded.
    """
    if os.environ.get("NO_COLOR"):
        return False
    try:
        if not sys.stdout.isatty():
            return False
        kernel32 = ctypes.windll.kernel32
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.GetStdHandle.argtypes = [wintypes.DWORD]

        handle = kernel32.GetStdHandle(_STD_OUTPUT_HANDLE)
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & _ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            return True
        return bool(
            kernel32.SetConsoleMode(
                handle, mode.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING
            )
        )
    except Exception:
        return False


def rust(text, enabled):
    """`text` in rusty red, or unchanged where colour is not available."""
    return f"{RUST}{text}{RESET}" if enabled else text


def _store_path(key, raw, label):
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise WrsrcliError(f"{path} is not an existing directory.")
    resolved = path.resolve()
    config.set_value(key, str(resolved))
    print(f"{label} path set to: {resolved}")


def resolve_path(key, detector):
    """A configured path if set, else autodetect and store it.

    SPEC.md 3: autodetection is attempted automatically the first time
    paths are needed if none are set; explicit values always win.
    """
    stored = config.get(key)
    if stored:
        return Path(stored)
    detected = detector()
    config.set_value(key, str(detected))
    return detected


def resolve_game_path():
    return resolve_path(config.GAME_PATH, steam.game_path)


def resolve_workshop_path():
    return resolve_path(config.WORKSHOP_PATH, steam.workshop_path)


def cmd_api(args):
    if args.remove:
        if args.key:
            raise WrsrcliError("`api --remove` does not take a key.")
        if config.remove(config.API_KEY):
            print("Steam Web API key removed.")
        else:
            print("No Steam Web API key was stored.")
        return 0

    if args.key:
        config.set_value(config.API_KEY, args.key)
        print(f"Steam Web API key stored in {config.config_path()}")
        return 0

    # No key and no --remove: report whether one is stored. The key itself
    # is never echoed back.
    if config.get(config.API_KEY):
        print("A Steam Web API key is stored.")
    else:
        print("No Steam Web API key is stored.")
    return 0


def cmd_scan(args):
    workshop_path = resolve_workshop_path()
    acf_path = steam.workshop_acf()
    if not acf_path.exists():
        raise WrsrcliError(f"{acf_path} not found — no workshop data to scan.")

    entries, warnings = scan.build(workshop_path, acf_path)

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    path = scan.write_manifest(entries)
    print(f"Scanned {len(entries)} installed item(s) from {workshop_path}")
    print(f"Manifest written to {path}")
    return 0


def _prompt_save_folder():
    raw = input(SAVE_PROMPT).strip().strip('"')
    folder = Path(raw).expanduser() if raw else Path.home() / "Documents"
    if not folder.is_dir():
        raise WrsrcliError(f"{folder} is not an existing directory.")
    return folder


def _resolve_output(folder):
    """The file to write, applying SPEC.md 4.2's collision prompt."""
    target = folder / OUTPUT_NAME
    if not target.exists():
        return target

    while True:
        choice = input(COLLISION_PROMPT).strip()
        if choice == "1":
            return target
        if choice == "2":
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M")
            return folder / f"WRSR Assets {stamp}.html"
        print("Please enter 1 or 2.")


def _enrich(key, entries):
    """Fetch Web API metadata. Returns (details, authors, api_mode).

    A failure here degrades to the local-only table rather than aborting a
    run that can still produce useful output (decision D-007).
    """
    item_ids = [e["item_id"] for e in entries if e.get("item_id")]
    owner_ids = sorted({e["owner_id"] for e in entries if e.get("owner_id")})

    try:
        details = steamapi.published_file_details(item_ids)
        authors = steamapi.player_names(key, owner_ids)
    except WrsrcliError as exc:
        print(f"warning: {exc}", file=sys.stderr)
        print(
            "warning: falling back to local data only — the table will omit "
            "author name, posted date and file size.",
            file=sys.stderr,
        )
        return None, None, False

    print(
        f"Retrieved Steam Web API metadata for {len(details)} item(s) and "
        f"{len(authors)} author(s)."
    )
    return details, authors, True


def cmd_output_table(args):
    key = config.get(config.API_KEY)
    if not key:
        print(NO_API_KEY_MESSAGE)
        print()

    entries = table.load_manifest()

    details, authors, api_mode = (None, None, False)
    if key:
        details, authors, api_mode = _enrich(key, entries)

    rows = table.build_rows(entries, resolve_workshop_path(), details, authors)

    destination = _resolve_output(_prompt_save_folder())
    try:
        destination.write_text(table.render(rows, api_mode), encoding="utf-8")
    except OSError as exc:
        raise WrsrcliError(f"could not write {destination}: {exc}") from exc

    print(f"Wrote {len(rows)} row(s) to {destination}")
    return 0


def _choose(prompt, count):
    """Prompt for a 1..count selection. ENTER returns None (cancel)."""
    while True:
        answer = input(prompt).strip()
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= count:
            return int(answer)
        print(f"Please enter a number from 1 to {count}, or press ENTER to cancel.")


def _resolve_conflicts(conflicts):
    """Settle every overlapping destination before anything is written (D-010)."""
    chosen = []
    skipped = []

    for destination, candidates in conflicts.items():
        print(f"\nConflict: {len(candidates)} sources map to {destination}")
        for index, candidate in enumerate(candidates, 1):
            when = importer.describe_mtime(candidate.source)
            print(f"   {index}. {candidate.source.name:<30} - modified {when}")
        print()

        pick = _choose("Please select which to copy (or press ENTER to skip this file): ", len(candidates))
        if pick is None:
            skipped.append(destination)
        else:
            chosen.append(candidates[pick - 1])

    return chosen, skipped


def _ensure_origin_present(item_id, workshop_root):
    """The origin item's folder, downloading it via SteamCMD if absent."""
    folder = workshop_root / item_id
    if folder.is_dir():
        return folder

    install_path = steam.steam_path() / "steamcmd"
    if not steamcmd.is_installed(install_path):
        raise WrsrcliError(
            f"origin item {item_id} is not installed locally and SteamCMD is not "
            "available to download it — run `wrsrcli steamcmd --install` first."
        )

    print(f"Origin item {item_id} is not installed locally. Downloading via SteamCMD ...")
    result, downloaded = steamcmd.download_workshop_item(install_path, APP_ID, item_id)
    if downloaded is None:
        raise WrsrcliError(
            f"SteamCMD could not download item {item_id} "
            f"(exit code {result.returncode}). Subscribe to it in Steam, or "
            "download it manually, then re-run this import."
        )
    print(f"Downloaded to {downloaded}")
    return downloaded


def _apply(recipe, list_path):
    """Plan, settle conflicts, then execute one import list.

    Shared by `import` and `manual-rerun` — a rerun goes through exactly
    the same planning and backup-before-write path (decision D-011).
    """
    game_path = resolve_game_path()
    workshop_root = resolve_workshop_path()
    origin_folder = _ensure_origin_present(recipe.item, workshop_root)

    # Plan everything and settle conflicts before touching a single file.
    planned, conflicts = importer.plan_copies(
        recipe.copies, origin_folder, game_path, workshop_root
    )
    if conflicts:
        chosen, skipped = _resolve_conflicts(conflicts)
        planned.extend(chosen)
        for destination in skipped:
            print(f"Skipped (conflict unresolved): {destination}")

    run = backup.Run(recipe.item)

    written = importer.execute_copies(planned, run)
    removed, missing = importer.execute_removals(
        recipe.removals, game_path, workshop_root, run
    )
    logged = run.commit()

    # Registered even when nothing was backed up, so every run is replayable.
    history.register(list_path, recipe.item, run.stamp)

    for raw in missing:
        print(f"warning: nothing to remove at {raw}", file=sys.stderr)

    print(f"\nCopied {written} file(s); removed {removed} target(s).")
    if logged:
        print(f"Backed up {logged} original(s) to {run.folder}")
    else:
        print("Nothing needed backing up — no existing files were overwritten.")
    return written, removed


def cmd_import(args):
    list_path = Path(args.path).expanduser()
    _apply(importlist.load(list_path), list_path)
    return 0


def cmd_manual_rerun(args):
    tracked = history.latest_per_origin()
    if not tracked:
        print("No import lists are tracked yet — run `wrsrcli import {path}` first.")
        return 0

    print(f"Re-applying {len(tracked)} tracked import list(s).")
    for origin, entry in sorted(tracked.items()):
        stored = Path(entry["stored_list"])
        if not stored.exists():
            print(
                f"warning: stored copy for {origin} is missing ({stored}) — skipped",
                file=sys.stderr,
            )
            continue
        print(f"\n--- {origin} (from {entry['list_path']}) ---")
        _apply(importlist.load(stored), stored)
    return 0


def cmd_manual_check(args):
    entries = backup.load()
    if not entries:
        print("No imports are tracked yet — nothing to check.")
        return 0

    acf_path = steam.workshop_acf()
    items = acf.parse(acf_path) if acf_path.exists() else {}

    flagged = staleness.check(entries, items)
    if not flagged:
        print(f"Checked {len(entries)} tracked change(s); nothing looks reverted.")
        return 0

    print(f"{len(flagged)} tracked change(s) may have been reverted:\n")
    for entry, reason in flagged:
        print(f"  {entry['original_path']}")
        print(f"    origin {entry['origin_steamid']} -> {entry['destination']}: {reason}")
    print("\nRun `wrsrcli manual-rerun` to re-apply the tracked import lists.")
    return 0


def _pick_generation(steamid, entries, verb):
    """Select one backup generation, prompting only if there are several."""
    grouped = backup.generations(entries)
    ordered = sorted(grouped.items(), key=lambda pair: pair[0][1], reverse=True)

    if len(ordered) == 1:
        return ordered[0][1]

    print(f"{len(ordered)} backup versions found for {steamid}. Select which to {verb}:")
    for index, ((origin, stamp), group) in enumerate(ordered, 1):
        counterpart = origin if verb == "restore" else group[0].get("destination", "?")
        label = "from" if verb == "restore" else "affecting"
        print(
            f"   {index}. {backup.describe(stamp)} - {label} {counterpart} "
            f"- {len(group)} file(s)"
        )
    print()

    pick = _choose("Please select (or press ENTER to cancel): ", len(ordered))
    return None if pick is None else ordered[pick - 1][1]


def _put_back(entries):
    """Return each backed-up file to its original location."""
    restored = 0
    for entry in entries:
        original = Path(entry["original_path"])
        stored = Path(entry["backup_path"])
        if not stored.exists():
            print(
                f"warning: backup missing for {original} (expected {stored})",
                file=sys.stderr,
            )
            continue
        try:
            original.parent.mkdir(parents=True, exist_ok=True)
            if stored.is_dir():
                shutil.copytree(stored, original, dirs_exist_ok=True)
            else:
                shutil.copy2(stored, original)
        except OSError as exc:
            raise WrsrcliError(f"could not restore {original}: {exc}") from exc
        restored += 1
    return restored


def cmd_restore(args):
    steamid = str(args.steamid)
    entries = [e for e in backup.load() if e.get("destination") == steamid]
    if not entries:
        print(f"No backups recorded with {steamid} as the destination.")
        return 0

    chosen = _pick_generation(steamid, entries, "restore")
    if chosen is None:
        print("Cancelled — nothing was changed.")
        return 0

    restored = _put_back(chosen)
    print(f"Restored {restored} file(s) belonging to {steamid}.")
    return 0


def cmd_rollback(args):
    steamid = str(args.steamid)
    entries = [e for e in backup.load() if e.get("origin_steamid") == steamid]
    if not entries:
        print(f"No backups recorded with {steamid} as the origin.")
        return 0

    chosen = _pick_generation(steamid, entries, "roll back")
    if chosen is None:
        print("Cancelled — nothing was changed.")
        return 0

    # A rollback undoes what this origin did: files it overwrote and files
    # it removed both come back from the backup store.
    restored = _put_back(chosen)
    print(f"Rolled back {restored} change(s) made by {steamid}.")
    return 0


def cmd_install(args):
    if not install.is_frozen():
        raise WrsrcliError(
            "`install` only applies to the standalone executable. You are running "
            "wrsrcli from a pip install, which already placed a `wrsrcli` script "
            "in that environment's Scripts folder."
        )

    directory = Path(args.path).expanduser() if args.path else install.default_directory()

    target = install.install(directory)
    print(f"Installed to {target}")

    if install.add_to_user_path(directory):
        print(f"Added {directory} to your PATH.")
        print("Open a new terminal, then `wrsrcli` will work from anywhere.")
    else:
        print(f"{directory} was already on your PATH.")

    return 0


def first_run():
    """Interactive flow for a double-clicked executable.

    Explorer closes the window the moment the process exits, so a bare
    argparse usage error would flash past unread. Someone who downloaded the
    .exe and double-clicked it wants to install it, so offer exactly that and
    always wait before exiting.
    """
    colour = enable_ansi()

    print(rust(FIRST_RUN_TITLE, colour))
    print(FIRST_RUN_BODY)

    prompt = (
        FIRST_RUN_PROMPT_BEFORE
        + rust(FIRST_RUN_PROMPT_KEY, colour)
        + FIRST_RUN_PROMPT_AFTER
    )

    # Only an empty line proceeds, matching `steamcmd --install` (D-008).
    try:
        answer = input(prompt + " ").strip()
    except EOFError:
        answer = "cancel"

    if answer:
        print("\nNot installed. You can run this file from a terminal instead,")
        print("or double-click it again later to install.")
    else:
        try:
            # Inside the try: a missing LOCALAPPDATA raises, and on this path
            # the message has to be shown rather than escape as a traceback.
            directory = install.default_directory()
            target = install.install(directory)
            print(f"\nInstalled to {target}")
            if install.add_to_user_path(directory):
                print(f"Added {directory} to your PATH.")
            else:
                print(f"{directory} was already on your PATH.")
            print()
            print("Open a NEW terminal window, then run:")
            print("    wrsrcli --help")
        except WrsrcliError as exc:
            print(f"\nInstall failed: {exc}")

    print()
    try:
        input("Press ENTER to close this window...")
    except EOFError:
        pass
    return 0


def cmd_uninstall(args):
    directory = Path(args.path).expanduser() if args.path else install.default_directory()

    removed, still_running = install.uninstall(directory)
    if removed:
        print(f"Removed {directory / install.BINARY_NAME}")
    elif still_running:
        print(f"{directory / install.BINARY_NAME} is the copy currently running,")
        print("so Windows will not let it delete itself. Delete it manually.")
    else:
        print(f"No installed copy found in {directory}")

    if install.remove_from_user_path(directory):
        print(f"Removed {directory} from your PATH.")
        print("Open a new terminal for that to take effect.")
    else:
        print(f"{directory} was not on your PATH.")

    print(
        "\nYour settings, manifest and backups in "
        f"{config.config_dir()} were left untouched."
    )
    return 0


def cmd_open_web(args):
    """Open the wrsrcli website in the user's default browser."""
    print(f"Opening {WEBSITE}")
    # `webbrowser` hands the URL to the OS default. It reports False when it
    # cannot find a browser to hand it to, in which case the printed URL is
    # the fallback and the user can copy it.
    if not webbrowser.open(WEBSITE):
        raise WrsrcliError(
            f"could not open a browser. Visit {WEBSITE} yourself instead."
        )
    return 0


def cmd_steamcmd(args):
    if not args.install:
        if args.path:
            raise WrsrcliError("`--path` only applies with `--install`.")
        print("wrsrcli steamcmd: nothing to do — pass -i/--install.", file=sys.stderr)
        return 1

    install_path = (
        Path(args.path).expanduser() if args.path else steam.steam_path() / "steamcmd"
    )

    if steamcmd.is_installed(install_path):
        print(f"SteamCMD is already installed at {install_path}")
        return 0

    print(STEAMCMD_PROMPT)
    # Only an empty line proceeds; anything else cancels (decision D-008).
    if input().strip():
        print("Cancelled — nothing was downloaded.")
        return 0

    print(f"Downloading SteamCMD from Valve to {install_path} ...")
    size = steamcmd.install(install_path)
    print(f"Downloaded and extracted {size:,} bytes.")

    print("Running steamcmd.exe once to let it self-update (this can take a while) ...")
    result = steamcmd.bootstrap(install_path)
    if result.returncode not in (0, 7):
        # 7 is SteamCMD's normal exit after a bare bootstrap on some builds.
        print(
            f"warning: steamcmd.exe exited with code {result.returncode} during "
            "its first run.",
            file=sys.stderr,
        )

    print(f"SteamCMD ready at {steamcmd.executable(install_path)}")
    return 0


def cmd_path(args):
    acted = False

    if args.auto_detect:
        # Detect first, so that an explicit -g/-w in the same invocation
        # overrides the detected value (SPEC.md 3).
        steam_root = steam.steam_path()
        print(f"Steam install: {steam_root}")

        detected_game = steam.game_path()
        config.set_value(config.GAME_PATH, str(detected_game))
        print(f"Game path detected: {detected_game}")

        detected_workshop = steam.workshop_path()
        config.set_value(config.WORKSHOP_PATH, str(detected_workshop))
        print(f"Workshop path detected: {detected_workshop}")
        acted = True

    if args.game:
        _store_path(config.GAME_PATH, args.game, "Game")
        acted = True

    if args.workshop:
        _store_path(config.WORKSHOP_PATH, args.workshop, "Workshop")
        acted = True

    if not acted:
        data = config.load()
        print(f"Game path:     {data.get(config.GAME_PATH) or '(not set)'}")
        print(f"Workshop path: {data.get(config.WORKSHOP_PATH) or '(not set)'}")

    return 0

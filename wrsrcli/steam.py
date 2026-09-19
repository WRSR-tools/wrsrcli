"""Locating Steam, its libraries, and the WRSR game/workshop folders.

Chain (SPEC.md 2.1): registry -> [STEAMPATH] -> libraryfolders.vdf ->
the library holding app 784150 -> game and workshop paths. The game
folder's name comes from that library's appmanifest `installdir` rather
than a hardcoded string (decision D-001).
"""

import winreg
from pathlib import Path

from . import APP_ID, vdf
from .errors import WrsrcliError

_REGISTRY_SUBKEY = r"Software\Valve\Steam"
_REGISTRY_VALUE = "SteamPath"


_lookup = vdf.lookup


def steam_path():
    """[STEAMPATH] from the Windows registry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_SUBKEY) as key:
            raw, _ = winreg.QueryValueEx(key, _REGISTRY_VALUE)
    except FileNotFoundError:
        raise WrsrcliError(
            "Steam is not registered on this machine "
            rf"(no {_REGISTRY_VALUE} under HKCU\{_REGISTRY_SUBKEY})."
        ) from None
    except OSError as exc:
        raise WrsrcliError(f"could not read the Steam path from the registry: {exc}")

    # Steam stores this with forward slashes; Path normalizes them.
    return Path(raw)


def library_folders(steam_root=None):
    """Every Steam library folder, from libraryfolders.vdf."""
    steam_root = steam_root or steam_path()
    manifest = steam_root / "steamapps" / "libraryfolders.vdf"
    if not manifest.exists():
        raise WrsrcliError(f"{manifest} not found — cannot enumerate Steam libraries.")

    data = vdf.load(manifest)
    root = _lookup(data, "libraryfolders")
    if root is None:
        raise WrsrcliError(f"{manifest} has no 'libraryfolders' block.")

    folders = []
    for entry in root.values():
        if not isinstance(entry, dict):
            continue
        path = _lookup(entry, "path")
        if path:
            folders.append(Path(path))
    if not folders:
        raise WrsrcliError(f"{manifest} lists no library folders.")
    return folders


def library_for_app(app_id=APP_ID, steam_root=None):
    """The library folder holding `app_id`, by its appmanifest."""
    for library in library_folders(steam_root):
        if (library / "steamapps" / f"appmanifest_{app_id}.acf").exists():
            return library
    raise WrsrcliError(
        f"app {app_id} is not installed in any Steam library — "
        "install the game, or set paths explicitly with `wrsrcli path`."
    )


def game_path(app_id=APP_ID, steam_root=None):
    """The game install folder, via the appmanifest's installdir (D-001)."""
    library = library_for_app(app_id, steam_root)
    manifest = library / "steamapps" / f"appmanifest_{app_id}.acf"

    state = _lookup(vdf.load(manifest), "AppState")
    installdir = _lookup(state, "installdir") if isinstance(state, dict) else None
    if not installdir:
        raise WrsrcliError(
            f"{manifest} has no 'installdir' — cannot determine the game folder. "
            'Set it explicitly with `wrsrcli path --game "{path}"`.'
        )

    resolved = library / "steamapps" / "common" / installdir
    if not resolved.exists():
        raise WrsrcliError(
            f"{manifest} gives installdir {installdir!r}, but {resolved} does not exist."
        )
    return resolved


def workshop_path(app_id=APP_ID, steam_root=None):
    """The workshop content folder for `app_id`."""
    library = library_for_app(app_id, steam_root)
    resolved = library / "steamapps" / "workshop" / "content" / app_id
    if not resolved.exists():
        raise WrsrcliError(
            f"{resolved} does not exist — no workshop items are downloaded for "
            f"app {app_id}."
        )
    return resolved


def workshop_acf(app_id=APP_ID, steam_root=None):
    """Path to appworkshop_{app_id}.acf (the subscribed/installed item list)."""
    library = library_for_app(app_id, steam_root)
    return library / "steamapps" / "workshop" / f"appworkshop_{app_id}.acf"

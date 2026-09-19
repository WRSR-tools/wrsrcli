"""Installing the standalone executable somewhere on the user's PATH.

The release build (Phase 10) produces a single `.exe`, which otherwise sits
wherever it was downloaded. This copies it to a per-user programs folder and
puts that folder on the user's PATH, so `wrsrcli` just works in a new shell.

Everything here is per-user: `%LOCALAPPDATA%\\Programs\\wrsrcli` and
`HKCU\\Environment`. No admin rights, and the machine-wide PATH is never
touched.
"""

import ctypes
import ctypes.wintypes as wintypes
import os
import shutil
import sys
import winreg
from pathlib import Path

from .errors import WrsrcliError

BINARY_NAME = "wrsrcli.exe"

# Windows' hard limit on an environment variable's value.
MAX_VALUE_LENGTH = 32767

_ENVIRONMENT_KEY = "Environment"
_PATH_VALUE = "Path"

# Tell running processes the environment changed, so new shells pick the
# PATH up without a sign-out. HWND_BROADCAST, WM_SETTINGCHANGE.
_HWND_BROADCAST = 0xFFFF
_WM_SETTINGCHANGE = 0x001A
_SMTO_ABORTIFHUNG = 0x0002

# Process enumeration, for identifying our parent. CreateToolhelp32Snapshot.
_TH32CS_SNAPPROCESS = 0x00000002
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_MAX_PATH = 260

# Explorer is the parent when a file is double-clicked, opened from its
# context menu, or launched from the Run dialog or the Start menu. Every one
# of those means "no terminal is waiting for this", which is what we are
# actually asking.
_EXPLORER = "explorer.exe"


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * _MAX_PATH),
    ]


def is_frozen():
    """True when running as the PyInstaller-built executable."""
    return getattr(sys, "frozen", False)


def ancestor_names(limit=8):
    """This process's ancestors' file names, lowercased, nearest first.

    One snapshot, walked once, collecting every PID's name and parent so the
    chain can be followed without further passes. A PID that has already
    exited may have been recycled, so a wrong answer is possible in
    principle; it only ever changes whether we offer to install, so it is not
    worth guarding against. `limit` and the seen-set bound the walk, because
    a recycled PID can otherwise produce a cycle.
    """
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == _INVALID_HANDLE_VALUE:
        return []

    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return []

        tree = {}
        while True:
            tree[entry.th32ProcessID] = (entry.szExeFile, entry.th32ParentProcessID)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)

    names = []
    pid = os.getpid()
    seen = set()
    while pid in tree and pid not in seen and len(names) < limit:
        seen.add(pid)
        name, parent = tree[pid]
        if pid != os.getpid():
            names.append(name.lower() if name else "")
        pid = parent
    return names


def launching_process_name():
    """The name of whatever actually started us, past our own bootloader.

    Not simply the parent. A PyInstaller `--onefile` build is two processes:
    the bootloader unpacks the payload to a temp folder and runs a *second*
    copy of the same executable, which is where this code runs. So the
    immediate parent is always our own `.exe` and the real launcher is a
    grandparent. Every leading generation sharing our executable's name is
    skipped for that reason.

    This is what B-001 turned on. Both of the original signals were defeated
    by the same detail — the parent was `wrsrcli.exe`, and the console had
    two processes attached rather than one, because the bootloader is
    attached too.
    """
    try:
        own = os.path.basename(sys.executable).lower()
    except Exception:
        own = ""
    for name in ancestor_names():
        if name and name != own:
            return name
    return None


def console_is_ours_alone():
    """True when this process is the only one attached to its console.

    The original — and until B-001 the only — double-click test. It cannot
    work in the shipped `--onefile` build, where the bootloader is attached
    to the same console and the count is never below two. Kept only as a
    second opinion for an unfrozen or one-folder build, where it does hold.
    """
    try:
        buffer = (ctypes.c_uint * 8)()
        count = ctypes.windll.kernel32.GetConsoleProcessList(buffer, 8)
    except Exception:
        return False
    return count == 1


def launched_from_explorer():
    """True when double-clicked rather than run from an existing terminal.

    Asking who started us answers this directly: Explorer means a
    double-click, a shell means a terminal is waiting. See
    `launching_process_name()` for why that question cannot be answered by
    looking at the immediate parent, which is what made B-001 survive its
    first fix.

    Either signal is enough. Neither fires when run from a shell, where the
    launcher is `powershell.exe`/`cmd.exe`/`pwsh.exe` and the console is
    shared, so a terminal user is never interrupted by the install prompt.
    """
    try:
        if launching_process_name() == _EXPLORER:
            return True
    except Exception:
        # Never let a detection failure turn into a crash on startup — the
        # worst outcome of getting this wrong is the ordinary usage message.
        pass
    return console_is_ours_alone()


def running_executable():
    return Path(sys.executable).resolve()


def default_directory():
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise WrsrcliError("LOCALAPPDATA is not set — cannot choose an install folder.")
    return Path(local) / "Programs" / "wrsrcli"


def _entries(raw):
    return [part for part in raw.split(";") if part.strip()]


def path_contains(raw, directory):
    """True if `directory` is already listed in the PATH string `raw`."""
    wanted = os.path.normcase(str(directory).rstrip("\\"))
    return any(os.path.normcase(part.rstrip("\\")) == wanted for part in _entries(raw))


def extend_path(raw, directory):
    """Return `raw` with `directory` appended, or None if already present.

    Kept as a pure function so the string handling can be tested without
    touching the registry — a mistake here would corrupt the user's PATH.
    """
    if path_contains(raw, directory):
        return None

    existing = raw.rstrip(";")
    updated = f"{existing};{directory}" if existing else str(directory)

    # Windows caps an environment variable at 32767 characters. Writing past
    # that truncates PATH, which would break the user's shell — so refuse and
    # let them choose a shorter location instead.
    if len(updated) > MAX_VALUE_LENGTH:
        raise WrsrcliError(
            f"adding {directory} would push your PATH past Windows' "
            f"{MAX_VALUE_LENGTH}-character limit "
            f"(it is already {len(raw)} characters). Refusing, rather than "
            "risk truncating it. Install somewhere shorter with "
            "`wrsrcli install -p \"{path}\"`, or tidy your PATH first."
        )
    return updated


def shrink_path(raw, directory):
    """Return `raw` without `directory`, or None if it was not there.

    Every other entry is preserved exactly as written — including blanks and
    unexpanded `%VAR%` segments — so uninstalling only ever removes our own
    entry and never quietly rewrites the rest of someone's PATH.
    """
    wanted = os.path.normcase(str(directory).rstrip("\\"))
    parts = raw.split(";")
    kept = [p for p in parts if os.path.normcase(p.strip().rstrip("\\")) != wanted]
    if len(kept) == len(parts):
        return None
    return ";".join(kept)


def read_user_path():
    """The user's PATH and its registry value type.

    A missing value means the user simply has no personal PATH yet, which is
    normal. Any other failure is reported rather than guessed at, because
    writing a wrong value here would break the user's shell.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ENVIRONMENT_KEY) as key:
            raw, value_type = winreg.QueryValueEx(key, _PATH_VALUE)
    except FileNotFoundError:
        return "", winreg.REG_EXPAND_SZ
    except OSError as exc:
        raise WrsrcliError(f"could not read your PATH from the registry: {exc}")

    if not isinstance(raw, str):
        raise WrsrcliError("your PATH registry value is not text — refusing to touch it.")
    return raw, value_type


def write_user_path(value, value_type):
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _ENVIRONMENT_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            # Preserve the original type: PATH is usually REG_EXPAND_SZ, and
            # rewriting it as REG_SZ would stop %VAR% entries expanding.
            winreg.SetValueEx(key, _PATH_VALUE, 0, value_type, value)
    except OSError as exc:
        raise WrsrcliError(f"could not update your PATH: {exc}") from exc


def broadcast_environment_change():
    """Best effort — a new shell works regardless."""
    try:
        ctypes.windll.user32.SendMessageTimeoutW(
            _HWND_BROADCAST, _WM_SETTINGCHANGE, 0, "Environment",
            _SMTO_ABORTIFHUNG, 5000, None,
        )
    except Exception:
        pass


def add_to_user_path(directory):
    """Append `directory` to the user PATH. Returns True if it changed."""
    raw, value_type = read_user_path()
    updated = extend_path(raw, directory)
    if updated is None:
        return False
    write_user_path(updated, value_type)
    broadcast_environment_change()
    return True


def remove_from_user_path(directory):
    """Drop `directory` from the user PATH. Returns True if it changed."""
    raw, value_type = read_user_path()
    updated = shrink_path(raw, directory)
    if updated is None:
        return False
    write_user_path(updated, value_type)
    broadcast_environment_change()
    return True


def uninstall(directory):
    """Remove the installed binary. Returns (removed, still_running_from_it).

    Windows will not let a running executable delete itself, so when
    uninstall is invoked via the installed copy the file is left in place
    and the caller reports that.

    Only the binary is touched. Config, the manifest and — importantly —
    the backup store all live in %APPDATA%\\wrsrcli and are left alone.
    """
    target = Path(directory) / BINARY_NAME
    if not target.exists():
        return False, False

    if target.samefile(running_executable()):
        return False, True

    try:
        target.unlink()
    except OSError as exc:
        raise WrsrcliError(f"could not remove {target}: {exc}") from exc

    # Clean up the folder only if our binary was the sole occupant.
    try:
        if not any(Path(directory).iterdir()):
            Path(directory).rmdir()
    except OSError:
        pass

    return True, False


def install(directory):
    """Copy the running executable into `directory`. Returns the new path."""
    source = running_executable()
    directory = Path(directory)
    target = directory / BINARY_NAME

    # Already installed and running from the target — copying a running
    # executable onto itself would fail on Windows anyway.
    if target.exists() and target.samefile(source):
        return target

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WrsrcliError(f"could not create {directory}: {exc}") from exc

    try:
        shutil.copy2(source, target)
    except OSError as exc:
        raise WrsrcliError(f"could not copy {source} to {target}: {exc}") from exc
    return target

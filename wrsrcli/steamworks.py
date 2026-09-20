"""Subscribing to workshop items through Valve's Steamworks API.

A subscription is the only way to have Steam install an item *and* keep it
updated: it writes the `.acf` entry, so `scan` sees the item like any other
and `latest_timeupdated` stays current. Everything else this tool can do —
SteamCMD downloads, opening the item's page — is a worse version of that.

The library is Valve's `steam_api64.dll`, bundled from the Steamworks SDK
and **not** covered by this project's Apache licence; see NOTICE and
THIRD-PARTY-NOTICES.md. Section 2.4 of Valve's agreement requires that
software interacting with Steamworks Services go through this API rather
than talking to those services directly, so this is the sanctioned route
rather than a shortcut around one.

Nothing here runs at import. `available()` is the single question the rest
of the tool asks, and every reason for "no" — the file is missing, it is
not the file we shipped, Steam is not running — is reported as itself.
"""

import ctypes
import hashlib
import sys
from pathlib import Path

# Steamworks SDK 1.65, redistributable_bin/win64/steam_api64.dll. Pinned so
# a substituted library is a refusal rather than arbitrary native code
# loaded into a process holding the user's Steam session.
DLL_SHA256 = "e6d9bafb9a41e42fba7b21553db49f8719027af3f0deb23ff86cfc44d60e776d"
DLL_NAME = "steam_api64.dll"
SDK_VERSION = "1.65"

APP_ID = 784150
UGC_VERSION = b"STEAMUGC_INTERFACE_VERSION021"

# isteamugc.h, enum EItemState.
SUBSCRIBED = 1
INSTALLED = 4
NEEDS_UPDATE = 8
DOWNLOADING = 16
DOWNLOAD_PENDING = 32
DISABLED_LOCALLY = 64

_STATE_NAMES = (
    (SUBSCRIBED, "subscribed"),
    (INSTALLED, "installed"),
    (NEEDS_UPDATE, "needs update"),
    (DOWNLOADING, "downloading"),
    (DOWNLOAD_PENDING, "download pending"),
    (DISABLED_LOCALLY, "disabled locally"),
)


def describe(bits):
    """Render an EItemState bitmask for humans."""
    named = [name for bit, name in _STATE_NAMES if bits & bit]
    return ", ".join(named) if named else "not tracked by Steam"


def dll_path():
    """Where the bundled library lives, frozen or not."""
    if getattr(sys, "frozen", False):
        # PyInstaller unpacks --add-binary content under _MEIPASS, keeping
        # the path it was added with.
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "wrsrcli" / "vendor" / "steamworks" / DLL_NAME
    return Path(__file__).parent / "vendor" / "steamworks" / DLL_NAME


def verify(path=None):
    """(ok, detail) for the library on disk. Never raises."""
    path = Path(path) if path else dll_path()
    if not path.exists():
        return False, f"{path} is not present"
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        return False, f"could not read {path}: {exc}"
    if digest != DLL_SHA256:
        return False, (
            f"{path} is not the library wrsrcli ships "
            f"(expected sha256 {DLL_SHA256[:16]}…, found {digest[:16]}…)"
        )
    return True, f"Steamworks SDK {SDK_VERSION}"


class Steamworks:
    """An initialised connection to the running Steam client.

    `SteamAPI_InitFlat` binds the *process* to an app id, so this is made
    once per run and never per item.
    """

    def __init__(self, api, ugc):
        self._api = api
        self._ugc = ugc

    def subscribe(self, item_id):
        """Subscribe. Returns Steam's call handle; the work is asynchronous."""
        return self._api.SteamAPI_ISteamUGC_SubscribeItem(self._ugc, int(item_id))

    def state(self, item_id):
        return self._api.SteamAPI_ISteamUGC_GetItemState(self._ugc, int(item_id))

    def pump(self):
        """Let Steam deliver results. Subscription progress needs this."""
        self._api.SteamAPI_RunCallbacks()

    def subscribed_count(self):
        return self._api.SteamAPI_ISteamUGC_GetNumSubscribedItems(self._ugc, False)

    def shutdown(self):
        try:
            self._api.SteamAPI_Shutdown()
        except OSError:
            pass


def connect(path=None):
    """(Steamworks, None) or (None, reason). Never raises.

    The caller decides what to do without it, so every failure is a reason
    a user can act on rather than an exception to surface raw.
    """
    import os

    ok, detail = verify(path)
    if not ok:
        return None, detail

    os.environ["SteamAppId"] = str(APP_ID)
    os.environ["SteamGameId"] = str(APP_ID)

    try:
        api = ctypes.CDLL(str(Path(path) if path else dll_path()))
    except OSError as exc:
        return None, f"could not load the Steamworks library: {exc}"

    try:
        # ESteamAPIInitResult SteamAPI_InitFlat( SteamErrMsg* ), where
        # SteamErrMsg is char[1024] and 0 is k_ESteamAPIInitResult_OK.
        api.SteamAPI_InitFlat.restype = ctypes.c_int
        api.SteamAPI_InitFlat.argtypes = [ctypes.c_char_p]
        message = ctypes.create_string_buffer(1024)
        result = api.SteamAPI_InitFlat(message)
        if result != 0:
            return None, (
                message.value.decode(errors="replace")
                or f"Steam could not be reached (code {result})"
            )

        api.SteamAPI_SteamUGC_v021.restype = ctypes.c_void_p
        ugc = api.SteamAPI_SteamUGC_v021()
        if not ugc:
            return None, "Steam did not provide the workshop interface"

        api.SteamAPI_ISteamUGC_SubscribeItem.restype = ctypes.c_uint64
        api.SteamAPI_ISteamUGC_SubscribeItem.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
        api.SteamAPI_ISteamUGC_GetItemState.restype = ctypes.c_uint32
        api.SteamAPI_ISteamUGC_GetItemState.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
        # bool bIncludeLocallyDisabled = false (isteamugc.h)
        api.SteamAPI_ISteamUGC_GetNumSubscribedItems.restype = ctypes.c_uint32
        api.SteamAPI_ISteamUGC_GetNumSubscribedItems.argtypes = [
            ctypes.c_void_p, ctypes.c_bool]
    except AttributeError as exc:
        return None, f"the Steamworks library is missing an expected entry point: {exc}"

    return Steamworks(api, ugc), None


def available(path=None):
    """Whether subscribing is possible right now, and why not if it isn't."""
    handle, reason = connect(path)
    if handle is None:
        return False, reason
    handle.shutdown()
    return True, None

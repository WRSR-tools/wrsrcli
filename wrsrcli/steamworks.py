"""Subscribing to workshop items through Valve's Steamworks API.

A subscription is the only way to have Steam install an item *and* keep it
updated: it writes the `.acf` entry, so `scan` sees the item like any other
and `latest_timeupdated` stays current. Fetching the files by any other
route leaves content Steam does not know about and will never update, which
is why this replaced the SteamCMD path entirely (D-024).

The same library answers what the Steam Web API used to: titles, owners,
published dates and an item's required items, with `ISteamFriends` for
author names and `GetItemInstallInfo` for size on disk.

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
import struct
import sys
import time
from pathlib import Path

# Steamworks SDK 1.65, redistributable_bin/win64/steam_api64.dll. Pinned so
# a substituted library is a refusal rather than arbitrary native code
# loaded into a process holding the user's Steam session.
DLL_SHA256 = "e6d9bafb9a41e42fba7b21553db49f8719027af3f0deb23ff86cfc44d60e776d"
DLL_NAME = "steam_api64.dll"
SDK_VERSION = "1.65"

APP_ID = 784150
UGC_VERSION = b"STEAMUGC_INTERFACE_VERSION021"

# SteamUGCDetails_t field offsets, measured against the shipped library
# rather than computed from the header's constants — the two disagree, and
# the binary is what is being read. `_plausible` re-checks every decode, so
# a layout change in a future SDK degrades to "no metadata" instead of
# quietly yielding nonsense.
#
# The struct is always written into an over-allocated buffer. Passing one
# that is too small makes Steam write past it and takes the process down
# with no traceback, which is not a failure mode worth risking on a
# calculation.
DETAILS_BUFFER = 65536
OFF_ID = 0
OFF_TITLE = 24
OFF_OWNER = 8160
OFF_CREATED = 8168
OFF_UPDATED = 8172
MAX_CHILDREN = 64

# SteamID64 for an individual account sits in this range.
STEAMID_MIN = 76561197960265728
STEAMID_MAX = 76561202255233024
# Sanity bounds for workshop timestamps: Steam predates neither.
TIME_MIN = 1000000000  # 2001
TIME_MAX = 4102444800  # 2100

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

    def subscribed_ids(self):
        """Every item this account is subscribed to, as strings."""
        count = self.subscribed_count()
        if not count:
            return []
        buf = (ctypes.c_uint64 * count)()
        got = self._api.SteamAPI_ISteamUGC_GetSubscribedItems(self._ugc, buf, count, False)
        return [str(buf[i]) for i in range(got)]

    def install_info(self, item_id):
        """(size_on_disk, folder, timestamp) for an installed item, or None.

        Read straight from the client, so it needs no struct offsets and no
        network — unlike the published metadata below.
        """
        size = ctypes.c_uint64(0)
        stamp = ctypes.c_uint32(0)
        folder = ctypes.create_string_buffer(1024)
        ok = self._api.SteamAPI_ISteamUGC_GetItemInstallInfo(
            self._ugc, int(item_id), ctypes.byref(size), folder, 1024, ctypes.byref(stamp)
        )
        if not ok:
            return None
        return size.value, folder.value.decode("utf-8", "replace"), stamp.value

    def wait_until(self, item_id, wanted, timeout=120):
        """Pump callbacks until `wanted` bits are set, or time runs out.

        Subscribing is asynchronous: Steam acknowledges immediately and
        downloads afterwards, so reporting success on the call alone would
        claim an install that has not happened.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump()
            bits = self.state(item_id)
            if bits & wanted:
                return bits
            time.sleep(0.25)
        return self.state(item_id)

    def _await_call(self, call, timeout=60):
        failed = ctypes.c_bool(False)
        utils = self._api.SteamAPI_SteamUtils_v011()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump()
            if self._api.SteamAPI_ISteamUtils_IsAPICallCompleted(
                utils, call, ctypes.byref(failed)
            ):
                return not failed.value
            time.sleep(0.1)
        return False

    def details(self, item_ids, timeout=60):
        """{item_id: {...}} published metadata, including dependencies.

        This is what the Steam Web API used to provide: title, owner,
        created/updated times and the item's required items. Items Steam
        declines to describe are simply absent.
        """
        wanted = [str(i) for i in item_ids]
        if not wanted:
            return {}

        found = {}
        # CreateQueryUGCDetailsRequest caps at 50 ids per request.
        for start in range(0, len(wanted), 50):
            batch = wanted[start : start + 50]
            ids = (ctypes.c_uint64 * len(batch))(*[int(i) for i in batch])
            query = self._api.SteamAPI_ISteamUGC_CreateQueryUGCDetailsRequest(
                self._ugc, ids, len(batch)
            )
            if not query:
                continue
            self._api.SteamAPI_ISteamUGC_SetReturnChildren(self._ugc, query, True)
            call = self._api.SteamAPI_ISteamUGC_SendQueryUGCRequest(self._ugc, query)
            if self._await_call(call, timeout):
                for index in range(len(batch)):
                    entry = self._read_details(query, index)
                    if entry:
                        found[entry["item_id"]] = entry
            self._api.SteamAPI_ISteamUGC_ReleaseQueryUGCRequest(self._ugc, query)

        return found

    def _read_details(self, query, index):
        buf = ctypes.create_string_buffer(DETAILS_BUFFER)
        if not self._api.SteamAPI_ISteamUGC_GetQueryUGCResult(self._ugc, query, index, buf):
            return None
        raw = buf.raw

        item_id = struct.unpack_from("<Q", raw, OFF_ID)[0]
        owner = struct.unpack_from("<Q", raw, OFF_OWNER)[0]
        created = struct.unpack_from("<I", raw, OFF_CREATED)[0]
        updated = struct.unpack_from("<I", raw, OFF_UPDATED)[0]
        if not _plausible(item_id, owner, created, updated):
            return None

        end = raw.find(b"\x00", OFF_TITLE)
        title = raw[OFF_TITLE:end].decode("utf-8", "replace") if end > OFF_TITLE else ""

        kids = (ctypes.c_uint64 * MAX_CHILDREN)()
        children = []
        if self._api.SteamAPI_ISteamUGC_GetQueryUGCChildren(
            self._ugc, query, index, kids, MAX_CHILDREN
        ):
            children = [str(kids[i]) for i in range(MAX_CHILDREN) if kids[i]]

        return {
            "item_id": str(item_id),
            "title": title,
            "owner_id": str(owner),
            "created": str(created),
            "updated": str(updated),
            "children": children,
        }

    def persona_names(self, owner_ids, timeout=5):
        """{steam_id: display name}. Names Steam will not supply are absent.

        Steam has these cached for anyone recently seen; for the rest it
        fetches in the background, so this asks and then waits briefly
        rather than blocking a scan on strangers' profiles.
        """
        wanted = [str(i) for i in owner_ids if str(i).isdigit()]
        if not wanted:
            return {}

        friends = self._api.SteamAPI_SteamFriends_v018()
        if not friends:
            return {}

        pending = []
        for steam_id in wanted:
            # True means Steam had to go and ask; False means it already knows.
            if self._api.SteamAPI_ISteamFriends_RequestUserInformation(
                friends, int(steam_id), True
            ):
                pending.append(steam_id)

        if pending:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                self.pump()
                time.sleep(0.2)
                if not any(
                    self._api.SteamAPI_ISteamFriends_RequestUserInformation(
                        friends, int(steam_id), True
                    )
                    for steam_id in pending
                ):
                    break

        names = {}
        for steam_id in wanted:
            raw = self._api.SteamAPI_ISteamFriends_GetFriendPersonaName(
                friends, int(steam_id)
            )
            name = raw.decode("utf-8", "replace") if raw else ""
            # Steam returns this placeholder when it has nothing.
            if name and name != "[unknown]":
                names[steam_id] = name
        return names

    def shutdown(self):
        try:
            self._api.SteamAPI_Shutdown()
        except OSError:
            pass


def _plausible(item_id, owner, created, updated):
    """Does a decoded record look like a record, rather than a misread?"""
    return (
        item_id > 0
        and STEAMID_MIN <= owner < STEAMID_MAX
        and TIME_MIN < created < TIME_MAX
        and TIME_MIN < updated < TIME_MAX
    )


_SIGNATURES = [
    ("ISteamUGC_SubscribeItem", ctypes.c_uint64, [ctypes.c_void_p, ctypes.c_uint64]),
    ("ISteamUGC_GetItemState", ctypes.c_uint32, [ctypes.c_void_p, ctypes.c_uint64]),
    ("ISteamUGC_GetNumSubscribedItems", ctypes.c_uint32, [ctypes.c_void_p, ctypes.c_bool]),
    ("ISteamUGC_GetSubscribedItems", ctypes.c_uint32,
     [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64), ctypes.c_uint32, ctypes.c_bool]),
    ("ISteamUGC_GetItemInstallInfo", ctypes.c_bool,
     [ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64),
      ctypes.c_char_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]),
    ("ISteamUGC_CreateQueryUGCDetailsRequest", ctypes.c_uint64,
     [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64), ctypes.c_uint32]),
    ("ISteamUGC_SetReturnChildren", ctypes.c_bool,
     [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_bool]),
    ("ISteamUGC_SendQueryUGCRequest", ctypes.c_uint64, [ctypes.c_void_p, ctypes.c_uint64]),
    ("ISteamUGC_GetQueryUGCResult", ctypes.c_bool,
     [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p]),
    ("ISteamUGC_GetQueryUGCChildren", ctypes.c_bool,
     [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32,
      ctypes.POINTER(ctypes.c_uint64), ctypes.c_uint32]),
    ("ISteamUGC_ReleaseQueryUGCRequest", ctypes.c_bool, [ctypes.c_void_p, ctypes.c_uint64]),
    ("ISteamUtils_IsAPICallCompleted", ctypes.c_bool,
     [ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_bool)]),
    ("ISteamFriends_RequestUserInformation", ctypes.c_bool,
     [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_bool]),
    ("ISteamFriends_GetFriendPersonaName", ctypes.c_char_p,
     [ctypes.c_void_p, ctypes.c_uint64]),
]


def _bind(api):
    """Declare every signature up front, from the SDK's own headers."""
    for name, restype, argtypes in _SIGNATURES:
        func = getattr(api, "SteamAPI_" + name)
        func.restype, func.argtypes = restype, argtypes
    api.SteamAPI_SteamUtils_v011.restype = ctypes.c_void_p
    api.SteamAPI_SteamFriends_v018.restype = ctypes.c_void_p


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

        _bind(api)
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

"""Steam Web API calls used to enrich `output-table` (SPEC.md 4.2).

Two endpoints:

- `ISteamRemoteStorage/GetPublishedFileDetails` — per-item file size and
  posted/updated dates.
- `ISteamUser/GetPlayerSummaries` — resolves a numeric `owner_id` to the
  author's display name. This one requires the key.

The stored API key is passed to Valve and never printed, logged, or
included in an error message. Exceptions raised here deliberately carry
only the endpoint name, never the request URL, because the key travels in
the query string of the GetPlayerSummaries call.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from .errors import WrsrcliError

PUBLISHED_FILE_DETAILS = (
    "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
)
PLAYER_SUMMARIES = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"

# Valve caps GetPlayerSummaries at 100 ids per call; the same batch size is
# comfortable for the file-details POST.
BATCH = 100
TIMEOUT = 20


def _request(url, data=None, label=""):
    """Fetch and JSON-decode. `label` names the endpoint for error messages."""
    try:
        with urllib.request.urlopen(url, data=data, timeout=TIMEOUT) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise WrsrcliError(
                f"Steam Web API rejected the stored key ({label}, HTTP {exc.code}). "
                "Check it with `wrsrcli api {key}`."
            ) from None
        raise WrsrcliError(f"Steam Web API error ({label}, HTTP {exc.code}).") from None
    except urllib.error.URLError as exc:
        raise WrsrcliError(f"could not reach the Steam Web API ({label}): {exc.reason}")
    except TimeoutError:
        raise WrsrcliError(f"the Steam Web API timed out ({label}).") from None

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        raise WrsrcliError(f"Steam Web API returned malformed JSON ({label}).") from None


def _chunks(values, size):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def published_file_details(item_ids):
    """{item_id: {file_size, time_created, time_updated}} for the given items."""
    details = {}

    for batch in _chunks(list(item_ids), BATCH):
        fields = {"itemcount": str(len(batch))}
        for index, item_id in enumerate(batch):
            fields[f"publishedfileids[{index}]"] = item_id

        body = urllib.parse.urlencode(fields).encode("utf-8")
        payload = _request(PUBLISHED_FILE_DETAILS, body, "GetPublishedFileDetails")

        for entry in payload.get("response", {}).get("publishedfiledetails", []):
            item_id = entry.get("publishedfileid")
            if not item_id:
                continue
            # result == 1 means the item was found; anything else (deleted,
            # private, wrong id) carries no usable metadata.
            if entry.get("result") not in (1, None):
                continue
            details[item_id] = {
                "file_size": entry.get("file_size"),
                "time_created": entry.get("time_created"),
                "time_updated": entry.get("time_updated"),
            }

    return details


def player_names(key, owner_ids):
    """{steam_id: display name} for the given owner ids."""
    names = {}

    for batch in _chunks(list(owner_ids), BATCH):
        query = urllib.parse.urlencode({"key": key, "steamids": ",".join(batch)})
        payload = _request(f"{PLAYER_SUMMARIES}?{query}", None, "GetPlayerSummaries")

        for player in payload.get("response", {}).get("players", []):
            steam_id = player.get("steamid")
            if steam_id:
                names[steam_id] = player.get("personaname") or ""

    return names

"""Knowing which version is current, and fetching a newer one (D-026).

Two sources, deliberately different:

- `versions/vX.Y.Z.txt` in the repository, one file per release, served raw.
  Each says whether it is the latest, and the release workflow rewrites the
  older ones when a new tag goes out. `--version` reads the one file naming
  its own build, so the answer costs a single small request and needs no API
  token, no rate limit and no JSON.
- the GitHub releases API, used only by `upgrade`, which needs the asset's
  download URL and so has to ask.

Nothing here raises for a network problem where the caller can carry on
without an answer: not knowing whether an upgrade exists is not a failure of
the command the user actually ran.
"""

import json
import urllib.error
import urllib.request
from pathlib import Path

from .errors import WrsrcliError

REPO = "WRSR-tools/wrsrcli"
VERSIONS_URL = f"https://raw.githubusercontent.com/{REPO}/main/versions"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME = "wrsrcli-windows-amd64.exe"

# `--version` runs this on every invocation, so it gives up quickly. Someone
# offline should not wait on a socket to be told their own version number.
STATUS_TIMEOUT = 2.5
DOWNLOAD_TIMEOUT = 120

USER_AGENT = "wrsrcli"


def _get(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def status_line(version, timeout=STATUS_TIMEOUT):
    """The published note for `version`, or None if it cannot be had.

    The file's own text is the message: the workflow writes "This is the
    latest version." and rewrites it when something newer ships, so this
    prints what it is given rather than deciding for itself.
    """
    try:
        raw = _get(f"{VERSIONS_URL}/v{version}.txt", timeout)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    # utf-8-sig: a byte-order mark would otherwise show up as an invisible
    # character at the front of the line this prints.
    line = raw.decode("utf-8-sig", "replace").strip().splitlines()
    return line[0].strip() if line else None


def latest_release(timeout=STATUS_TIMEOUT * 4):
    """(tag, download URL) for the newest release. Raises if it cannot ask."""
    try:
        payload = json.loads(_get(LATEST_RELEASE_URL, timeout))
    except urllib.error.HTTPError as exc:
        raise WrsrcliError(
            f"GitHub returned HTTP {exc.code} when asked for the latest release."
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WrsrcliError(f"could not reach GitHub: {exc}") from None
    except json.JSONDecodeError:
        raise WrsrcliError("GitHub returned something that is not JSON.") from None

    tag = payload.get("tag_name") or ""
    for asset in payload.get("assets") or []:
        if asset.get("name") == ASSET_NAME:
            return tag, asset.get("browser_download_url")
    raise WrsrcliError(
        f"release {tag or '(unnamed)'} has no {ASSET_NAME} attached — "
        "download it from the releases page instead."
    )


def download(url, destination, timeout=DOWNLOAD_TIMEOUT):
    """Fetch `url` to `destination`. Returns the byte count."""
    destination = Path(destination)
    try:
        payload = _get(url, timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WrsrcliError(f"could not download {url}: {exc}") from None

    # A truncated or error-page download must not be handed to the replacer:
    # `MZ` is the first thing in every Windows executable.
    if not payload.startswith(b"MZ"):
        raise WrsrcliError(
            f"what was downloaded is not a Windows executable "
            f"({len(payload)} bytes). Nothing has been changed."
        )

    try:
        destination.write_bytes(payload)
    except OSError as exc:
        raise WrsrcliError(f"could not write {destination}: {exc}") from exc
    return len(payload)


def normalise(tag):
    """`v1.2.3` and `1.2.3` compare equal."""
    return (tag or "").strip().lstrip("vV")

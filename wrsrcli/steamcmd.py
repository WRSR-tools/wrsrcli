"""Installing and invoking SteamCMD (SPEC.md 3).

This is the only part of wrsrcli that downloads and executes third-party
code. It runs solely from `wrsrcli steamcmd --install`, behind the
verbatim confirmation prompt, and only an empty line proceeds (D-008).

Nothing here ever supplies Steam credentials: workshop downloads are
attempted anonymously. If an item needs an account, that is reported to
the user to handle in SteamCMD themselves.
"""

import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .errors import WrsrcliError

# The official archive, as published on Valve's SteamCMD wiki page.
ZIP_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"

DOWNLOAD_TIMEOUT = 120
BOOTSTRAP_TIMEOUT = 600
WORKSHOP_TIMEOUT = 900


def executable(install_path):
    return Path(install_path) / "steamcmd.exe"


def is_installed(install_path):
    return executable(install_path).exists()


def download_zip(destination):
    """Fetch the SteamCMD zip to `destination`. Returns bytes written."""
    try:
        with urllib.request.urlopen(ZIP_URL, timeout=DOWNLOAD_TIMEOUT) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise WrsrcliError(
            f"could not download SteamCMD from Valve (HTTP {exc.code})."
        ) from None
    except urllib.error.URLError as exc:
        raise WrsrcliError(f"could not reach Valve to download SteamCMD: {exc.reason}")
    except TimeoutError:
        raise WrsrcliError("timed out downloading SteamCMD from Valve.") from None

    try:
        destination.write_bytes(payload)
    except OSError as exc:
        raise WrsrcliError(f"could not write {destination}: {exc}") from exc
    return len(payload)


def extract(archive, install_path):
    try:
        install_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WrsrcliError(f"could not create {install_path}: {exc}") from exc

    try:
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(install_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise WrsrcliError(f"could not extract the SteamCMD archive: {exc}") from exc

    if not is_installed(install_path):
        raise WrsrcliError(
            f"the SteamCMD archive did not contain steamcmd.exe "
            f"(extracted to {install_path})."
        )


def invoke(install_path, arguments, timeout):
    """Run steamcmd.exe with `arguments`. Returns a CompletedProcess."""
    exe = executable(install_path)
    if not exe.exists():
        raise WrsrcliError(
            f"{exe} not found — run `wrsrcli steamcmd --install` first."
        )

    try:
        return subprocess.run(
            [str(exe), *arguments],
            cwd=str(install_path),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise WrsrcliError(
            f"SteamCMD did not finish within {timeout}s."
        ) from None
    except OSError as exc:
        raise WrsrcliError(f"could not run {exe}: {exc}") from exc


def bootstrap(install_path):
    """First run — SteamCMD downloads its own updates, then quits."""
    return invoke(install_path, ["+quit"], BOOTSTRAP_TIMEOUT)


def install(install_path):
    """Download, extract and bootstrap SteamCMD. Returns bytes downloaded."""
    install_path = Path(install_path)

    with tempfile.TemporaryDirectory(prefix="wrsrcli-steamcmd-") as workspace:
        archive = Path(workspace) / "steamcmd.zip"
        size = download_zip(archive)
        extract(archive, install_path)

    return size


def download_workshop_item(install_path, app_id, item_id):
    """Fetch one workshop item anonymously. Returns (CompletedProcess, path).

    `path` is SteamCMD's own content folder for the item if it appeared,
    else None. No credentials are ever supplied; items that require an
    account will fail here and must be handled by the user directly.
    """
    result = invoke(
        install_path,
        [
            "+login",
            "anonymous",
            "+workshop_download_item",
            str(app_id),
            str(item_id),
            "+quit",
        ],
        WORKSHOP_TIMEOUT,
    )

    downloaded = (
        Path(install_path)
        / "steamapps"
        / "workshop"
        / "content"
        / str(app_id)
        / str(item_id)
    )
    return result, (downloaded if downloaded.exists() else None)

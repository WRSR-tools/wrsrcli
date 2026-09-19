# wrsrcli — Specification

A Windows CLI tool to inventory, document, and manage Steam Workshop assets
for *Workers & Resources: Soviet Republic* (WRSR, Steam app ID `784150`).

Status: design settled through discussion; not yet implemented. Items
marked **OPEN** are explicitly undecided and must not be guessed at during
implementation — implement around them or stop and ask.

---

## 1. Scope and non-goals

- Windows only for v1. No SteamCMD-free downloading — all downloads go
  through SteamCMD.
- No file-watching / background daemon. Every command runs once, on
  demand, and exits.

- CLI first. A Tauri webview UI is a possible future phase, not part of
  this spec.

---

## 2. Local data sources

### 2.1 Steam registry / library files

- Steam's install path: Windows registry,
  `HKEY_CURRENT_USER\Software\Valve\Steam\SteamPath`. This is `[STEAMPATH]`.
- Installed library folders: `libraryfolders.vdf`, under `[STEAMPATH]/steamapps/`.
- Subscribed/installed workshop items for app 784150:
  `steamapps/workshop/appworkshop_784150.acf`, within whichever library
  folder has it.
  - `.acf` has two blocks over the same item IDs:
    - `WorkshopItemsInstalled` — has `size`, `timeupdated`, `manifest` per item.
    - `WorkshopItemDetails` — has `timeupdated`, `timetouched`,
      `subscribedby`, `manifest` per item; **no** `size`.
  - An item present in `WorkshopItemDetails` but **not** in
    `WorkshopItemsInstalled` is subscribed-but-not-downloaded.
- Workshop content folder: `steamapps/workshop/content/784150/{item_id}/`.
- Game install folder: `steamapps/common/{installdir}/`, where
  `{installdir}` is read from the `"installdir"` key in
  `steamapps/appmanifest_784150.acf` in whichever library folder holds app
  `784150`. Not hardcoded — see decision D-001. On a stock install this
  resolves to `steamapps/common/SovietRepublic/`; the display name
  `Workers & Resources: Soviet Republic` is the manifest's `"name"` field,
  not the directory name. If the manifest is missing or has no
  `installdir`, autodetect fails and reports so rather than guessing; the
  user sets the path explicitly with `wrsrcli path --game "{path}"`.

### 2.2 `workshopconfig.ini`

Each downloaded workshop item's folder contains a `workshopconfig.ini` in
Valve's own `$KEY value` syntax — it ships with every workshop download,
so an item lacking one has had the file deleted locally (see decision
D-005 for how `scan` handles that) (not real INI, not YAML, not JSON — a
line-oriented `$-prefixed` key/value format, with a `$END` terminator).
Confirmed fields, from a real sample:

```
$ITEM_ID 3779842468
$OWNER_ID 76561198050524085
$ITEM_TYPE WORKSHOP_ITEMTYPE_BUILDING
$VISIBILITY 2
$TAGS 2
$TAGS 13
$OBJECT_BUILDING FreeHeliportParking
$OBJECT_BUILDING FreeHeliportCargo
$ITEM_NAME "Free Helipad & Cargo Heliports [1.1.1.9]"
$ITEM_DESC "...multi-line BBCode..."
$END
```

Notes:

- `$TAGS` may repeat (multiple tag lines per item).
- `$OBJECT_BUILDING` (and presumably `$OBJECT_VEHICLE` for vehicle items)
  may repeat.
- `$ITEM_DESC` is a multi-line, quoted, BBCode-formatted block.
- `$OWNER_ID` is numeric only — no display name available locally.
- **Not present:** author display name, file size, posted date, updated
  date. These require the Steam Web API.
- **OPEN:** meaning of numeric `$TAGS` values (e.g. `2`, `13`) is not yet
  known. v1 displays raw tag values as-is; a human-readable mapping is
  deferred to a later version.

---

## 3. Configuration and state

All persistent local state lives in `%APPDATA%\wrsrcli\` — **never** inside
the project repository. This includes `config.json` (API key, workshop
path, game path) and the backup manifest. Because this lives outside the
repo, it never needs `.gitignore` handling.

### `wrsrcli api {key}`

Sets the Steam Web API key. Overwrites any existing key.

### `wrsrcli api -r` / `wrsrcli api --remove`

Removes the stored API key.

### `wrsrcli path -g "{path}"` / `wrsrcli path --game "{path}"`

Sets the game install path explicitly.

### `wrsrcli path -w "{path}"` / `wrsrcli path --workshop "{path}"`

Sets the workshop content path explicitly.

### `wrsrcli path -a` / `wrsrcli path --auto-detect`

Attempts to autodetect both paths from the Windows registry (see §2.1)
and stores the results. Autodetection is also attempted automatically the
first time paths are needed if none are set; explicit `-g`/`-w` always
override autodetected values.

### `wrsrcli install`

Only meaningful for the standalone `.exe` from a release (Phase 10). Copies
the running executable to `%LOCALAPPDATA%\wrsrcli`-style per-user storage —
specifically `%LOCALAPPDATA%\Programs\wrsrcli\wrsrcli.exe` — and adds that
folder to the **user** PATH, so `wrsrcli` works from any new terminal.

- `-p "{path}"` / `--path "{path}"` installs elsewhere.
- Idempotent: never appends a duplicate PATH entry.
- Refuses when not running as the frozen executable, since a pip install
  has already placed a `wrsrcli` script in its environment's Scripts folder.
- Per-user only: `HKCU\Environment`, never the machine-wide PATH, so no
  admin rights are required.

See decision D-014.

### First run: the double-clicked executable

The standalone `.exe` run with no arguments, from Explorer rather than from
a terminal, shows the installer screen instead of an argparse usage error.
Detection of "from Explorer" identifies the launching process, looking
past our own PyInstaller bootloader generations; see B-001.

Printed verbatim — do not reword:

```
wrsrcli dev - Workshop Manager for Workers and Resources: Soviet Republic
================================================================================
This is the installer for the wrsrcli - a command line tool to manage workshop
assets for Workers and Resources: Soviet Republic.

For more information on how to use this tool, please visit:
   https://wrsr-tools.github.io

   Press ENTER to install...
```

- The **title line and the prompt** are rendered in rusty red; the rest is
  plain. Colour is used only where the console has been confirmed to handle
  ANSI escapes, and is suppressed when `NO_COLOR` is set or output is not a
  terminal. See decision D-016.
- **Only an empty line (ENTER) proceeds**, matching `steamcmd --install`
  (D-008). Any other input cancels and nothing is installed.
- On ENTER the behaviour is exactly `wrsrcli install`'s: the executable is
  copied to the default directory and that directory is added to the user
  PATH, with both reported.
- The window always waits for a final ENTER before exiting, because Explorer
  closes it the instant the process does.

### `wrsrcli uninstall`

Reverses `wrsrcli install`. Removes the installed `wrsrcli.exe` and takes
its folder back off the user PATH.

- `-p "{path}"` / `--path "{path}"` uninstalls from a non-default location,
  matching the `-p` given to `install`.
- Windows will not let a running executable delete itself, so when
  `uninstall` is invoked *via* the installed copy the binary is left in
  place and the user is told to remove it by hand. The PATH entry is still
  removed.
- Removing the PATH entry preserves every other entry exactly as written,
  including blank segments and unexpanded `%VAR%` values.
- The install folder is removed only if our binary was its sole occupant.
- **`%APPDATA%\wrsrcli\` is never touched** — config, manifest and the
  entire backup store survive an uninstall, so uninstalling can never cost
  the user a file an import overwrote.

See decision D-015, which supersedes D-014's exclusion of an uninstall path.

### `wrsrcli steamcmd -i` / `wrsrcli steamcmd --install`

Installs SteamCMD. Default install location: `[STEAMPATH]/steamcmd`. An
alternate path is given with `-p "{path}"` / `--path "{path}"` (decision
D-008); the directory is created if it does not exist. `-p` without `-i`
is a usage error.

On running, prints, verbatim:

```
Press ENTER to automatically download and install steamcmd from Valve. If you prefer to download and install yourself, please open this link:
   https://developer.valvesoftware.com/wiki/SteamCMD
```

- **Only an empty line (ENTER) proceeds.** Any other input cancels and
  nothing is downloaded (decision D-008).
- On ENTER: `wrsrcli` downloads the official SteamCMD zip from Valve,
  extracts it to the install path, and runs `steamcmd.exe` once (which
  self-bootstraps/updates on first run). This is the only place in the
  tool that downloads and executes third-party code automatically, and it
  is always gated behind this explicit confirmation.
- No separate "manual install" code path is needed — the printed link is
  the manual option, handled outside `wrsrcli` entirely.

---

## 4. Commands

### 4.1 `wrsrcli scan`

Builds `manifest.json` at `%APPDATA%\wrsrcli\manifest.json` (decision
D-003) from the local workshop folder and `.acf` file. One entry per
installed workshop item, as a JSON array:

```json
{
  "item_id": "3780739284",
  "owner_id": "76561198050524085",
  "item_type": "WORKSHOP_ITEMTYPE_SCRIPT",
  "date_updated": "1788306308",
  "date_touched": "1789051884"
}
```

- `date_updated` / `date_touched` are sourced from the `.acf` file
  (`timeupdated`/`timetouched` in `WorkshopItemDetails`), not filesystem
  timestamps — filesystem mtimes can be wrong after a copy/restore. They
  are stored as the raw Unix timestamp strings the `.acf` holds;
  formatting is left to `output-table`.
- There is deliberately no `date_created`: no creation date exists in any
  local source. The item's posted date comes from the Steam Web API
  (§4.2, Phase 5). See decision D-004.
- `owner_id` and `item_type` are **nullable**. They come from
  `workshopconfig.ini`; if that file has been deleted locally the entry is
  still written, with those two fields null and a warning naming the item.
  See decision D-005.

### 4.2 `wrsrcli output-table`

Reads `manifest.json` (does not re-scan) and renders a static, searchable,
filterable, sortable HTML table — one self-contained `.html` file, data
embedded as JSON, vanilla JS for search/filter/sort (no external
framework/CDN dependency, since the output file must work standalone,
indefinitely, with no network access).

**Step 1 — API key check.** If no Steam Web API key is stored, print,
verbatim:

```
Steam Web API key has not been set. To retrieve metadata from Steam, please obtain an API key from:
   https://steamcommunity.com/dev/apikey

wrsrcli will now build an HTML table of your assets using workshopconfig.ini.
```

Then proceed using only locally available data (§2.2): Item ID, folder
name, `$ITEM_NAME`, `$ITEM_TYPE`, `$TAGS` (raw values), `$OWNER_ID`
(numeric only, no resolved name), plus `.acf`-derived dates. No file size,
no resolved author name, no separately-sourced posted date.

If an API key **is** set, additionally query the Steam Web API
(`ISteamRemoteStorage/GetPublishedFileDetails` for item metadata including
file size and posted/updated dates; `ISteamUser/GetPlayerSummaries` to
resolve `owner_id` to a display name) and include those enriched fields.

**Step 2 — save location.** Prompt, verbatim:

```
Please enter path to save folder, or press ENTER to use Documents. The filename will be WRSR Assets.html:
```

**Step 3 — collision handling.** If `WRSR Assets.html` already exists at
the chosen path, prompt, verbatim:

```
WRSR Assets.html found. Do you want to:
   1. Overwrite the current file
   2. Append a timestamp to the new file

Please select:
```

- Timestamp format for option 2: `WRSR Assets
  YYYY-MM-DD HH-mm.html`.

**Table columns:** Item ID, Name (`$ITEM_NAME` — see decision D-006; the
folder name is not shown separately, because folder names *are* item IDs),
Item Type (category) / raw `$TAGS` values (subcategory — meaning not yet
mapped, see §2.2), Owner ID, Updated date. In API mode, additionally:
Author name (replacing Owner ID), Posted date, File size.

In no-API mode the Author name, Posted date and File size columns are
omitted rather than rendered empty — this section's own no-API data list
gives no local source for any of them ("No file size, no resolved author
name, no separately-sourced posted date").

### 4.3 `wrsrcli import {path}`

Reads a user-authored YAML import list (format below) describing file
operations to apply for a given workshop item.

**YAML schema:**

```yaml
item: 3780739284
copy:
  - src: foldernamehere/
    dst: "[GAME]/media_soviet/signs/"
  - src: "*"
    dst: "[GAME]/media_soviet/signs/"
  - src: signscript.txt
    dst: "[GAME]/media_soviet/signs/"
  - src: foldername/somescript.txt
    dst: "[WORKSHOP]/000000000000000/"
remove:
  - "[GAME]/media_soviet/signs/foldertodelete/"
  - "[GAME]/media_soviet/signs/filetodel.ete"
```

- `item`: the origin workshop item ID this import list applies to.
- `copy`: list of `{src, dst}` pairs. `src` is relative to the origin
  item's workshop folder. `dst` uses `[GAME]` or `[WORKSHOP]/{id}/` as
  path placeholders, resolved via the configured/autodetected game path
  and the target item's workshop folder respectively.
  - `src: "*"` means **everything in the origin item's workshop folder,
    except `workshopconfig.ini`** (that exclusion is fixed, not
    user-configurable in v1).
  - Copying into `[WORKSHOP]/{id}/` (another item's own folder) is
    intentional — supports import lists that patch/alter another mod's
    files.
  - Conflict/overwrite order when multiple `copy` entries
    (e.g. `*` and a specific named file) target overlapping destinations:
    surface to the user and present selectable options with the dates of
    the candidate source files. An overlap is two or more entries
    resolving the same destination file from *different* sources;
    detection runs after `*`/directory expansion and before any file is
    written, and ENTER skips that destination. See decision D-010.
- `remove`: list of destination paths to remove. Always in `[GAME]` or
  `[WORKSHOP]/{id}/` space (destination paths, not origin-relative).

**Execution order for `import {path}`:**

1. Check whether the origin item (`item:` field) is already present
   locally. If not, download it via SteamCMD first.
2. Execute all `copy` operations.
3. Execute all `remove` operations.
4. Every file touched by `copy` (overwritten) or `remove` (taken away) is
   backed up first — **nothing is ever hard-deleted.** See §5.

### 4.4 `wrsrcli restore {steamid}`

Restores the **destination** steamid's original files — i.e. undoes
overwrite/removal damage done *to* `{steamid}` by any import(s). If
multiple origin items have overwritten files belonging to this
destination (multiple backup generations), prompts the user to select
which version to restore (see §5).

### 4.5 `wrsrcli rollback {steamid}`

Undoes changes that importing **origin** item `{steamid}` introduced
elsewhere — i.e. undoes damage done *by* `{steamid}`'s import. If this
origin item has been imported multiple times (multiple generations of its
own changes), prompts the user to select which version to roll back (see
§5). Files that were `remove`'d by this origin's import are restored from
backup as part of rollback.

### 4.6 `wrsrcli manual-rerun`

Re-executes the `copy`/`remove` operations of all previously-run import
lists currently tracked (i.e. reapplies them). Intended for the case where
Steam has silently reverted files (see §4.7) — manual-only, no automatic
detection or scheduling; runs only when invoked.

Tracked lists live in `%APPDATA%\wrsrcli\imports.json`, with a verbatim
copy of each list at `%APPDATA%\wrsrcli\imports\{origin}\{stamp}.yaml`
(decision D-011 — the backup manifest in §5 cannot describe a `copy`'s
source, so it alone is not enough to replay an import). The most recent
registered list per origin item is replayed, through the same planning,
conflict-resolution and backup-before-write path as a first-time import.

### 4.7 `wrsrcli manual-check`

Because Steam can silently revert manually-placed files (on workshop item
update or verify, or on game update/verify), this command checks every
tracked backup entry for staleness and flags candidates for
`manual-rerun`:

- For a backup entry whose **destination** is a workshop item
  (`[WORKSHOP]/{id}/`): compare that destination item's `.acf`
  `timeupdated` (§2.1) against the backup entry's recorded timestamp. If
  `.acf` is newer, the destination has been touched by Steam since the
  backup was made → flag.
- For a backup entry whose **destination** is `[GAME]/...`: no `.acf`
  applies to game files. Instead, compare the file's current mtime against
  the entry's `placed_mtime` — the mtime the file had immediately after the
  import wrote it. If it is newer → flag. Entries predating that field fall
  back to comparing against the entry's `timestamp`.
  - `placed_mtime` exists because `copy2` preserves the *source's* mtime,
    so a freshly-imported file does not carry the time of the copy.
    Comparing against the backup's timestamp instead would flag every
    import the moment it finished. See decision D-012.
  - Known limitation: this check can still false-positive (anything
    touching the file's mtime without changing content would trigger it).
    Accepted for v1, not solved.
  - Known limitation: only backed-up files are tracked. An import that
    *adds* files without overwriting anything creates no backup entries,
    so those files are not checked for reversion.
- If a destination has multiple backup generations, compare against the
  most recent relevant entry.

---

## 5. Backup manifest

Every `copy` (overwrite) or `remove` action performed by `import` is
logged before it happens. Nothing is ever permanently deleted — a
`remove`'d file is moved into a backup folder (`%APPDATA%\wrsrcli\backups\`), not erased.

**Per-entry schema:**

| Field            | Meaning                                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------- |
| `origin_steamid` | The item whose import list caused this change.                                                          |
| `destination`    | The steamid whose files were affected, or `"vanilla"` for base game files with no owning workshop item. |
| `action`         | `"copy"` (overwrite) or `"remove"`.                                                                     |
| `original_path`  | Path of the file before the action.                                                                     |
| `backup_path`    | Where the original/removed file was moved to.                                                           |
| `timestamp`      | When this backup entry was created.                                                                     |

**Terminology:** *origin* = the item whose import caused a change;
*destination* = the item or game-file location that was changed.

**Storage layout** (decision D-009): the manifest is
`%APPDATA%\wrsrcli\backups.json`; backed-up files live at
`%APPDATA%\wrsrcli\backups\{origin}\{YYYYMMDD-HHMMSS}\{nnn}_{filename}`,
one timestamped folder per `import` run (one run = one generation). Two
runs of the same origin inside one second get a `-2`, `-3`, ... suffix, so
a generation can never reuse another's folder and overwrite its backups.
The
original location is recorded only in the manifest's `original_path`, not
encoded in the backup path, which keeps backup paths short and immune to
Windows' 260-character limit.

**Multi-version prompt:** applies to both `restore` and `rollback`. If the
given steamid has more than one relevant backup generation — as a
destination hit by multiple origins (`restore`), or as an origin imported
multiple times (`rollback`) — the user is asked to choose which version
to act on. Wording and behavior per decision D-009; generations are listed
newest first with timestamp, counterpart steamid and file count, and ENTER
cancels. A single generation is acted on without prompting.

---

## 6. Known open items (do not guess — flag or ask)

1. Meaning of numeric `$TAGS` values in `workshopconfig.ini` (category/
   subcategory mapping) — deferred, raw values shown for now.
2. ~~Exact game install folder name under `steamapps/common/`.~~
   **CLOSED** by decision D-001 (2026-09-19): resolved at runtime from
   `appmanifest_784150.acf`'s `installdir` key, not hardcoded. See §2.1.
   *(Item numbering retained so existing `EXECUTION-PLAN.md` references
   stay valid.)*
3. ~~`manifest.json` output location.~~ **CLOSED** by decision D-003
   (2026-09-19): `%APPDATA%\wrsrcli\manifest.json`, no path argument.
   See §4.1.
4. ~~Alternate-path flag syntax for `wrsrcli steamcmd --install`.~~
   **CLOSED** by decision D-008 (2026-09-19): `-p` / `--path`, and only
   ENTER confirms the download. See §3.
5. ~~Exact wording/UI for the multi-version restore/rollback prompt.~~
   **CLOSED** by decision D-009 (2026-09-19). See §5.
6. ~~GitHub Actions build trigger for the `.exe` release (push / tag /
   manual dispatch).~~ **CLOSED** by decision D-013 (2026-09-19): tags
   matching `v*` plus `workflow_dispatch`, building
   `wrsrcli-windows-amd64.exe` on `windows-latest`. See
   `EXECUTION-PLAN.md` Phase 10 and `.github/workflows/release.yml`.

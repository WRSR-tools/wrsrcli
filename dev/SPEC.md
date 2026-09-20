# wrsrcli — Specification

A Windows CLI tool to inventory, document, and manage Steam Workshop assets
for *Workers & Resources: Soviet Republic* (WRSR, Steam app ID `784150`).

Status: design settled through discussion; not yet implemented. Items
marked **OPEN** are explicitly undecided and must not be guessed at during
implementation — implement around them or stop and ask.

---

## 1. Scope and non-goals

- Windows only for v1. Installing workshop items means **subscribing**
  through the running Steam client, via Valve's Steamworks SDK
  redistributable (decision D-024). wrsrcli never downloads workshop
  content itself and never handles Steam credentials.
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
      `subscribedby`, `manifest` per item; **no** `size`. It also carries
      `latest_timeupdated` and `latest_manifest` — Steam's own record of
      the newest published version it knows of, as of `TimeLastFullCheck`.
      Comparing `timeupdated` against `latest_timeupdated` answers "is this
      out of date" with no API call (decision D-022).
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
  date. `scan` collects these from the running Steam client and stores
  them in the manifest (§4.1, D-024).
- **OPEN:** meaning of numeric `$TAGS` values (e.g. `2`, `13`) is not yet
  known. v1 displays raw tag values as-is; a human-readable mapping is
  deferred to a later version.

---

## 3. Configuration and state

All persistent local state lives in `%APPDATA%\wrsrcli\` — **never** inside
the project repository. This includes `config.json` (workshop
path, game path) and the backup manifest. Because this lives outside the
repo, it never needs `.gitignore` handling. There is no stored API key:
since D-024 all Steam data comes from the running client.

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

Printed verbatim — do not reword. The version in the title is major.minor
from `__version__`, so it tracks the build rather than being typed out:

```
wrsrcli v0.1 - Workshop Manager for Workers and Resources: Soviet Republic
================================================================================
This is the installer for the wrsrcli - a command line tool to manage workshop
assets for Workers and Resources: Soviet Republic.

For more information on how to use this tool, please visit:
   https://wrsr-tools.github.io

   Press ENTER to install...
```

- The **title line** is rendered in rusty red, and within the prompt only the
  word `ENTER`; everything else is left uncoloured. Colour is used only where
  the console has been confirmed to handle ANSI escapes, and is suppressed
  when `NO_COLOR` is set or output is not a terminal. See decisions D-016 and
  D-017.
- **Only an empty line (ENTER) proceeds**, matching every other prompt
  (D-008). Any other input cancels and nothing is installed.
- On ENTER the behaviour is exactly `wrsrcli install`'s: the executable is
  copied to the default directory and that directory is added to the user
  PATH, with both reported.
- The window always waits for a final ENTER before exiting, because Explorer
  closes it the instant the process does.

### `wrsrcli open-web`

Opens the project website, `https://wrsr-tools.github.io/`, in the user's
default browser. The URL is printed first, so it remains usable when no
browser can be launched; failure to launch one is reported as an error
naming the URL. See decision D-017.

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

---

## 4. Commands

`wrsrcli --help`, and `wrsrcli` with no arguments (D-017), list the
commands below. Section headings, command names, option strings and the
`usage:` prefix are shown in the rusty red of D-016; descriptions keep the
terminal's own foreground. The same colour rules as the first-run screen
apply — the accent appears only where the console has been confirmed to
handle ANSI escapes, and never when `NO_COLOR` is set or output is
redirected. Python 3.14's own colourised help is suppressed in favour of
this. See D-019.

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
  "date_touched": "1789051884",
  "dependencies": [
    {
      "item_id": "3787969749",
      "name": "Republic Mod Loader [1.1.1.9]",
      "creator_id": "76561198050524085",
      "creator": "UltimateUniverse"
    }
  ]
}
```

- `date_updated` / `date_touched` are sourced from the `.acf` file
  (`timeupdated`/`timetouched` in `WorkshopItemDetails`), not filesystem
  timestamps — filesystem mtimes can be wrong after a copy/restore. They
  are stored as the raw Unix timestamp strings the `.acf` holds;
  formatting is left to `output-table`.
- There is deliberately no `date_created`: no creation date exists in any
  local source. The item's posted date comes from Steam, collected by
  `scan` as `date_published` (D-024). See decision D-004.
- `owner_id` and `item_type` are **nullable**. They come from
  `workshopconfig.ini`; if that file has been deleted locally the entry is
  still written, with those two fields null and a warning naming the item.
  See decision D-005.
- `dependencies` is the item's Steam-declared **required items**, one
  object each, empty where the item declares none, read from
  `ISteamUGC` (D-024). `name`, `creator_id` and `creator` are stored
  because an unmet dependency has no local folder to read them from.
  Whether a dependency is *installed* is deliberately **not** stored; it
  is derived at render time from the manifest's own entries, so the two
  cannot disagree. See decision D-020.
- `title`, `author`, `date_published` and `size_on_disk` likewise come from
  Steam and are written here so that `output-table` needs neither Steam nor
  a network. `title` and `author` also fill in an item whose
  `workshopconfig.ini` was deleted locally, which D-005 could only leave
  blank.
- "Installed" means the `.acf` **or** a numeric folder in the workshop
  directory. Since D-024 nothing wrsrcli does puts files outside Steam, so
  a folder Steam has no record of was placed by something else: it is still
  inventoried, and always warned about, naming the consequence — Steam will
  never update it.
- With Steam not running, the enrichment fields are **absent**
  and the rest of the manifest is written as normal, with a warning. The
  local inventory is the job `scan` does not fail at. A scan that did
  reach the API also reports how many items declare dependencies and
  names any that are not installed.

### 4.2 `wrsrcli output-table`

Reads `manifest.json` (does not re-scan) and renders a static, searchable,
filterable, sortable HTML table — one self-contained `.html` file, data
embedded as JSON, vanilla JS for search/filter/sort (no external
framework/CDN dependency, since the output file must work standalone,
indefinitely, with no network access).

**Step 1 — nothing to check.** Since D-024 every column has a local
source: `workshopconfig.ini` for the display name and tags, and the
manifest for the title, author, published date, size and dependencies that
`scan` collected from Steam. `output-table` makes no network call and needs
no Steam client, so there is no key prompt and no reduced mode.

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
folder name is not shown separately, because folder names *are* item IDs;
falling back to Steam's title where the config file was deleted), Item Type
(category), raw `$TAGS` values (subcategory — meaning not yet mapped, see
§2.2), Author, Posted date, Updated date, Size on disk.

One column set, always. The two-mode rendering went with the Web API in
D-024.

**Links.** The Item ID cell links to the item's workshop page
(`https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}`), and
the Author cell — Owner ID in no-API mode — links to the creator's profile
(`https://steamcommunity.com/profiles/{owner_id}`). Both open in a new tab
with `rel="noopener noreferrer"`. A hyperlink is navigation, not a
resource the page loads, so the file remains standalone with zero external
references in the sense this section requires. Cells with no id to link
are rendered as plain text.

**Status accordions.** Two accordions sit above the controls, each headed
with its own state so it reads without being opened. A clean one is green
and collapsed; a problem one is red and open, since a "nothing to do" panel
has nothing worth unfolding and a red one is why the user is looking. The
colour pairs are contrast-checked against their own tint in both themes
(measured 5.82:1 and 6.64:1 light, 8.95:1 and 8.51:1 dark).

`Dependencies (OK)` / `(Dependencies missing)` reads the manifest, so it
appears whenever dependencies have been scanned, key or not:

```
Dependencies OK. No further action needed.
```
```
The following items have unmet dependencies:
   - {steamid} {assetname_linked} ({creatorname})

Run `wrsrcli update` to download all dependencies.
```

`Asset status (OK)` / `(Update needed)` compares the installed version
against the newest published one, using the `.acf`'s own
`latest_timeupdated` as captured by `scan` (D-022). `update` itself asks
Steam directly instead (D-024). Where the manifest carries no
`date_latest`, the accordion is **absent** rather than claiming everything
is current:

```
All assets are up to date. No further action is needed.
```
```
The following items need to be updated:
   - {steamid} {assetname_linked} ({creatorname})

Run `wrsrcli update` to update.
```

The panel adds, in muted text: "Checked against Steam's own record, as of
its last sync. Run `wrsrcli update` for a live check." Steam's cached view is
worth acting on, but it is not a live check and is not presented as one —
`wrsrcli update` asks Steam directly.

Both lists link the item id, the name and the creator. The Updated column
shows the **installed** version's date, not the workshop's — showing the
remote value there would display a version the user does not have and hide
the condition this accordion reports (decision D-021, superseding the
earlier preference for the API's `time_updated`).

**Dependencies.** Where the manifest carries `dependencies` (§4.1), each
such row gets a fold-down, collapsed by default, opened by a toggle in a
leading column. That column is present whenever any row has dependencies —
in both modes, since a stored dependency is local data once scanned —
and absent entirely when none do. The fold is headed `DEPENDENCY` for one
and `DEPENDENCIES` for more, and lists:

```
- {steamid} {asset name} ({creator}) (OK|Not installed)
```

`OK` means the dependency is among the manifest's installed items; `Not
installed` is emphasised in the accent colour. The item id and the creator
are themselves links, as above. See decision D-020.

### 4.3 `wrsrcli import {path}`

Reads a user-authored YAML import list (format below) describing file
operations to apply for one or more workshop items. The markup is defined
by WMLS — `dev/wmls/standard.v1.md` is the normative document; this
section records what `wrsrcli` implements of it.

**YAML schema (WMLS `v1`):**

```yaml
version: 1

items:
  - item: 3780739284
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
    depends-mandatory:
      - item: 3621284903
    depends-optional:
      - item: 3111111111
        message: "Short message shown when the user is asked whether to install"
```

- `version`: the WMLS version the file is written to. Required. This build
  understands `version: 1`; any other value is an error.
- `items`: the list of origin items the file describes. Required, non-empty,
  and used even when there is only one item. An item may appear only once.
- `item`: the origin workshop item ID this entry applies to.
- `copy`: list of `{src, dst}` pairs. `src` is relative to the origin
  item's workshop folder. `dst` uses `[GAME]` or `[WORKSHOP]/{id}/` as
  path placeholders, resolved via the configured/autodetected game path
  and the target item's workshop folder respectively.
  - `src: "*"` means **everything in the origin item's workshop folder,
    except `workshopconfig.ini`** (that exclusion is fixed, not
    user-configurable in v1). `*` is not a wildcard inside a path —
    `src: "signs/*"` is rejected; `src: "signs/"` copies that folder.
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
- `depends-mandatory`: items the origin needs. Each is `{item}`. They are
  downloaded without asking if absent; a download that fails aborts the
  item's import.
- `depends-optional`: items the origin benefits from. Each is
  `{item, message}`; `message` is required and is what the user is shown
  when asked. ENTER downloads, anything else skips (D-008, D-018).

**Backwards compatibility.** A file with no `version:` line is the `beta`
markup — a single top-level `item:` with its own `copy:`/`remove:` and no
dependencies. It is still applied, with a deprecation warning on stderr.
See decision D-018.

**Execution order for `import {path}`:**

Each item in `items` is processed in turn, in file order. One item is one
backup generation. For each item:

1. Resolve `depends-mandatory`, then `depends-optional`, subscribing
   through Steam to anything not already installed and waiting for it to
   finish installing (D-024).
2. Check whether the origin item (`item:` field) is already present
   locally. If not, subscribe to it first and wait for the install.
3. Execute all `copy` operations.
4. Execute all `remove` operations.
5. Every file touched by `copy` (overwritten) or `remove` (taken away) is
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

### 4.8 `wrsrcli update`

Subscribes to everything the inventory says is needed: dependencies
referenced by an installed item but not installed, and items with a newer
version published. Reads `manifest.json`; run `scan` first.

**Which items qualify.**

- *Missing dependencies* come from the manifest's `dependencies` (§4.1).
- *Out of date* is `ISteamUGC::GetItemState` reporting `NeedsUpdate` —
  Steam's own answer, with no timestamps compared. An item already
  downloading is not reported, since it is being dealt with.

**Prompt.** Everything to be subscribed is listed first, then:

```
Press ENTER to subscribe, or anything else to cancel:
```

Only ENTER proceeds. Subscribing changes the user's Steam account, so it is
the action AGENTS.md's opt-in rule now guards.

**What happens.** `ISteamUGC::SubscribeItem` per item, then callbacks are
pumped until Steam reports the item installed or a timeout elapses.
Subscribing is acknowledged immediately and downloaded afterwards, so
reporting success on the call alone would claim an install that has not
happened. An item that does not reach `Installed` is reported with the
state it did reach, and the command exits non-zero.

Steam installs into its own workshop folder, writes the `.acf` entry and
keeps the item updated from then on. Nothing is backed up because nothing
is overwritten. Afterwards the user is told to re-run `scan`.

Requires the Steam client running, with the signed-in account owning the
game. See decision D-024.

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

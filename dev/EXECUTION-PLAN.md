# wrsrcli — Execution Plan

Build order for the commands defined in `SPEC.md`. Each phase has a
concrete verification step — don't mark a phase done until its check
passes. Phases are ordered so each one only depends on capabilities built
in an earlier phase.

Status: not started.

---

## Phase 0 — Project skeleton

1. Python project structure (single package, CLI entry point via
   `argparse` or similar — stdlib preferred per `AGENTS.md`).
2. `wrsrcli --help` lists all subcommands from §4 of `SPEC.md` (stubs are
   fine at this point — no logic yet).

**Verify:** `wrsrcli --help` runs and lists every command name from the
spec.

---

## Phase 1 — Config and path detection

Implements §3 of `SPEC.md`.

1. `%APPDATA%\wrsrcli\config.json` read/write helpers.
2. `wrsrcli api {key}` / `wrsrcli api -r`.
3. Windows registry read for `[STEAMPATH]`.
4. `libraryfolders.vdf` parser (enough to enumerate library folders).
5. `wrsrcli path --auto-detect`, `--game`, `--workshop`.

**Verify:**
- `wrsrcli api {key}` then re-running `wrsrcli api` (or an inspection
  command) shows the key is stored; `wrsrcli api -r` clears it.
- On the dev machine, `wrsrcli path --auto-detect` finds the real Steam
  install and WRSR workshop/game paths and reports them correctly.
- `wrsrcli path --game "{path}"` overrides the autodetected value.

---

## Phase 2 — `.acf` and `workshopconfig.ini` parsing

Implements §2.1–2.2. This is the foundation `scan` and `output-table`
both depend on.

1. `appworkshop_784150.acf` parser — both `WorkshopItemsInstalled` and
   `WorkshopItemDetails` blocks.
2. `workshopconfig.ini` parser for Valve's `$KEY value` format (repeating
   keys like `$TAGS`, `$OBJECT_BUILDING`; multi-line quoted `$ITEM_DESC`;
   `$END` terminator).

**Verify:** against the real sample in `SPEC.md` §2.2 — item `3779842468`
is present in the local workshop folder, so parse its actual
`workshopconfig.ini` and check the resulting record by hand against the
raw file contents, not just "it didn't crash." Include an item with
repeating `$TAGS`/`$OBJECT_BUILDING` lines and a multi-line `$ITEM_DESC`.

---

## Phase 3 — `wrsrcli scan`

Implements §4.1. Depends on Phase 1 (paths) and Phase 2 (`.acf` parsing).

1. Enumerate installed workshop items from `.acf`.
2. Write `manifest.json` (schema per §4.1; output location per open item
   #3 — resolve or flag before writing this phase's code).

**Verify:** run `wrsrcli scan` against the real workshop folder → produces
a valid `manifest.json` with one entry per installed item. Confirm a
sampled entry's fields match the `.acf` data by hand-inspection.

---

## Phase 4 — `wrsrcli output-table` (no-API-key path first)

Implements §4.2, minus Steam Web API enrichment. Depends on Phase 2
(`workshopconfig.ini` parsing) and Phase 3 (manifest as input).

1. API-key-check message (verbatim per spec) when no key is stored.
2. Build table rows from `manifest.json` + `workshopconfig.ini` only.
3. Save-location prompt and overwrite/timestamp collision prompt
   (both verbatim per spec; timestamp format is specified in §4.2 —
   `WRSR Assets YYYY-MM-DD HH-mm.html`).
4. Render self-contained HTML: embedded JSON data, vanilla JS
   search/filter/sort, no external/CDN dependencies.

**Verify:** run without an API key set → correct message printed, table
built from local data only, opens correctly in a browser, search/filter/
sort work against the real workshop folder's items.

---

## Phase 5 — Steam Web API enrichment

Extends Phase 4. Depends on an API key being available (Phase 1).

1. `ISteamRemoteStorage/GetPublishedFileDetails` call — file size, posted/
   updated dates.
2. `ISteamUser/GetPlayerSummaries` call — resolve `owner_id` → author
   display name.
3. Wire enrichment into `output-table` when a key is present.

**Verify:** with a real API key and at least one real subscribed item,
`output-table`'s output includes correct author name, file size, and
dates, cross-checked against the item's actual Steam Workshop page.

---

## Phase 6 — SteamCMD install and invocation

Implements the `wrsrcli steamcmd --install` part of §3. Depends on Phase 1
(`[STEAMPATH]` detection).

1. Confirmation prompt (verbatim per spec).
2. Download SteamCMD zip from Valve, extract to `[STEAMPATH]/steamcmd`
   (or chosen path — resolve open item #4, the alternate-path flag,
   before this step).
3. Run `steamcmd.exe` once to trigger self-bootstrap.
4. A minimal wrapper for invoking SteamCMD to download a specific
   workshop item by app ID + item ID (needed by Phase 7).

**Verify:** SteamCMD is already installed at the default target on the dev
machine (`[STEAMPATH]/steamcmd`), so verify against a throwaway path
instead — this exercises the same alternate-path flag that open item #4
covers, and leaves the existing install untouched. Running
`wrsrcli steamcmd --install` at that path and pressing ENTER results in a
working `steamcmd.exe` that can be invoked to download a known public
workshop item.

---

## Phase 7 — `wrsrcli import`

Implements §4.3. Depends on Phase 1 (paths), Phase 6 (SteamCMD
invocation), and the backup mechanism (Phase 8 — build these together, as
`import` cannot safely run without backup-on-write).

1. YAML import-list parser matching the schema in `SPEC.md` §4.3.
2. Presence check for the origin item; SteamCMD download if missing.
3. `copy` execution, honoring `*` = everything except
   `workshopconfig.ini`. Where multiple `copy` entries target overlapping
   destinations, §4.3 specifies the behavior: surface the conflict to the
   user and present selectable options with the dates the change occurred.
4. `remove` execution (move to backup, never delete — see Phase 8).

**Verify:** hand-crafted import list against a disposable test copy of a
game folder — confirm files end up copied/removed exactly as specified,
and that nothing is permanently deleted (originals are recoverable from
the backup folder).

---

## Phase 8 — Backup manifest, `restore`, `rollback`

Implements §5, §4.4, §4.5. Built alongside Phase 7 since `import` depends
on backup-before-write.

1. Backup manifest read/write (schema per §5; backup folder location is
   specified in §5 — `%APPDATA%\wrsrcli\backups\`).
2. Backup-before-write hook used by `import`'s `copy`/`remove` execution.
3. `wrsrcli restore {steamid}` — query backup manifest for entries where
   this steamid is the `destination`; single-version case first, then
   multi-version prompt (resolve open item #5 — prompt wording — before
   implementing the prompt).
4. `wrsrcli rollback {steamid}` — query backup manifest for entries where
   this steamid is the `origin_steamid`; same single/multi-version
   structure as `restore`.

**Verify:** run an `import` that overwrites a known test file, confirm
`restore` on the destination steamid brings back the original file
byte-for-byte; confirm `rollback` on the origin steamid removes what it
introduced and restores anything it removed. Manually create a
multi-generation backup scenario and confirm the selection prompt appears
and both choices resolve correctly.

---

## Phase 9 — `manual-rerun` and `manual-check`

Implements §4.6, §4.7. Depends on Phase 7/8 (import history exists to act
on).

1. `manual-rerun` — replay stored import lists' `copy`/`remove`
   operations.
2. `manual-check` — staleness comparison: `.acf` `timeupdated` for
   `[WORKSHOP]/`-destination entries, filesystem mtime for
   `[GAME]/`-destination entries (per §4.7).

**Verify:** manually edit/replace a file that `import` had placed
(simulating a Steam revert), confirm `manual-check` flags the correct
steamid, confirm `manual-rerun` restores the expected state.

---

## Phase 10 — Packaged `.exe` release

Implements the build/release side referenced by `SPEC.md` §6 item 6.
Depends on Phase 9 (feature-complete CLI).

1. Package the CLI as a standalone Windows `.exe`. This adds a build-time
   dependency (PyInstaller or equivalent) — it is a CI/build dependency
   only, not a runtime import, so it does not change the stdlib-first rule
   for the tool itself.
2. GitHub Actions workflow to produce the `.exe` and attach it to a
   release. Trigger resolved by decision D-013 (open item #6): tags
   matching `v*`, plus `workflow_dispatch`. Windows-only, since `winreg`
   makes other platforms impossible.

**Verify:** the workflow produces an `.exe` that runs `wrsrcli --help`
successfully on a Windows machine with no Python installed.

**Status:** the `.exe` is built and confirmed working (`--version`,
`--help`, `winreg` via `path --auto-detect`, and bundled PyYAML via a full
`import` run, from a cleared environment outside the repo). The "no Python
installed" half of the criterion is **not** verified — it needs a machine
without Python, which the dev machine is not. See D-013.

---

## Notes for whoever (human or agent) picks this up

- Resolve or explicitly flag each numbered open item in `SPEC.md` §6
  before or during the phase that needs it — don't silently invent an
  answer.
- Every phase's "Verify" step is the actual success criterion for that
  phase, per the Karpathy goal-driven-execution principle in
  `AGENTS.md`. Don't mark a phase complete without running it.
- Phases 3–5 (scan/output-table/API) verify against the real workshop
  folder, which currently holds 21 installed items — enough for a
  meaningful multi-row table in Phase 4. Phase 5 additionally needs a
  Steam Web API key, which is the only outstanding prerequisite.

# AGENTS.md

Instructions for AI coding agents working in this repository.

## What this project is

`wrsrcli` is a Windows command-line tool for managing Steam Workshop assets
for *Workers & Resources: Soviet Republic* (WRSR, Steam app ID 784150). It
scans the local workshop folder, builds a JSON manifest of installed assets,
renders a searchable HTML overview, and can apply user-authored "import
lists" that copy/remove files into the game or into other workshop items'
folders (with backup/restore/rollback).

Full behavioral spec: see `dev/SPEC.md`. Build order: see
`dev/EXECUTION-PLAN.md`. Current status: see `dev/Progress.md`. The
records kept under `dev/` and their formats are defined in
`dev/REPO-STRUCTURE.md`.

## Stack

- **Language:** Python (CLI first). A Tauri webview UI is a possible later
  phase — do not build toward it unless asked.
- **Target platform:** Windows only. Do not add cross-platform abstractions
  that aren't needed yet (see Simplicity, below).
- **Dependencies:** stdlib first. Only reach for a third-party package when
  the stdlib genuinely can't do it cleanly (e.g. YAML parsing — Python's
  stdlib has no YAML support, so `PyYAML` is expected there). Justify any
  other new dependency before adding it.
- **Config/state location:** never inside the repo. All local state (API
  key, workshop/game paths, backup manifest) lives in the OS config
  directory (Windows: `%APPDATA%\wrsrcli\`), never in the project folder.
  This means it never needs `.gitignore` handling — it simply isn't here.

## Principles (apply to all work in this repo, not just code)

These are the standing rules for how to work here — read them before making
changes, not just before writing new code.

1. **Think before coding.** State assumptions explicitly. If multiple
   reasonable interpretations exist, present them — don't silently pick
   one. If something in `SPEC.md` is ambiguous or contradicts the code,
   stop and ask rather than guessing.
2. **Simplicity first.** Build the minimum that satisfies the current spec
   and execution-plan step. No speculative abstractions, no
   "configurability" nobody asked for, no error handling for scenarios
   that can't occur given this tool's actual inputs.
3. **Surgical changes.** Touch only what a given change requires. Don't
   refactor or reformat adjacent code. Match existing style. If you notice
   something unrelated that looks wrong, say so — don't fix it silently.
   Remove imports/variables that your own change orphaned; don't remove
   pre-existing dead code unless asked.
4. **Goal-driven execution.** Every non-trivial change should have a
   stated, checkable success criterion (a test that passes, a command
   whose output matches a documented example, etc.) before it's considered
   done.

## Security-relevant rules — do not violate these

- **Never commit or hardcode the Steam Web API key**, anywhere, in any
  file in this repo — not even as an example or placeholder that looks
  real. It is supplied by each user via `wrsrcli api {key}` and stored in
  `%APPDATA%\wrsrcli\config.json`, outside the repo entirely.
- **Never write code that performs a hard delete** of a file that
  `import`/`copy`/`remove` operations touch. Every overwrite or removal
  must go through the backup mechanism described in `SPEC.md` first.
- **SteamCMD and file downloads are the only network/subprocess actions
  a user must explicitly opt into** (`wrsrcli steamcmd --install` shows a
  confirmation prompt before downloading anything). Don't add other
  automatic downloads or subprocess execution without an equivalent,
  explicit user-facing prompt.

## Development record-keeping

`dev/REPO-STRUCTURE.md` defines the development records kept in this repo
and the exact filename and body format for each. Follow it — these are
part of doing the work, not paperwork to catch up on afterwards.

- **Progress tracker (`dev/Progress.md`).** Log an entry at both the
  **start and the end of every phase** in `dev/EXECUTION-PLAN.md`. The
  end-of-phase entry is written only once that phase's "Verify" step has
  actually been run and passed — a phase is not done because the code
  exists, it is done because its success criterion was checked (see
  Principle 4).
- **Decisions (`dev/decisions/`).** Any resolution of an open item in
  `SPEC.md` §6, or any other non-obvious call, gets a `D-NNN` record
  before the code that depends on it is written. Record the tradeoffs, not
  just the conclusion.
- **Bugs (`dev/bugs/`).** Logged as `B-NNN` records.

Where a record and the code disagree, that is drift worth reporting — say
so rather than quietly bringing one into line with the other.

## Working conventions

- Command-line interface: one subcommand per verb (`scan`, `output-table`,
  `update`, `import`, `restore`, `rollback`, `manual-rerun`, `manual-check`,
  `api`, `path`, `install`, `uninstall`, `open-web`, `steamcmd`), matching the
  definitions in `SPEC.md`. Adding a verb means updating this list and
  `SPEC.md` in the same change — `install` and `uninstall` were both
  implemented before either was recorded (see D-015).
- When a spec detail is marked "open" or "deferred" in `SPEC.md`, do not
  invent an answer — implement the narrowest version that satisfies what
  *is* specified, and leave the open item open (flag it, don't guess).

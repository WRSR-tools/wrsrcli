# Import lists

Some WRSR assets are not installed simply by subscribing. They ship files
that have to be copied into the game's own folders, or that replace files
belonging to another mod. An **import list** is a small YAML file that
describes those file operations once, so `wrsrcli` can apply them for you
and, just as importantly, undo them.

Nothing an import touches is ever hard-deleted. Every file it overwrites
and every file it removes is copied into the backup store **before** the
destructive step, so `restore` and `rollback` always have something real to
put back.

## The format

```yaml
item: 3780739284

copy:
  - src: signs/
    dst: "[GAME]/media_soviet/signs/"
  - src: signscript.txt
    dst: "[GAME]/media_soviet/signs/"
  - src: patch/building.ini
    dst: "[WORKSHOP]/3621284903/"

remove:
  - "[GAME]/media_soviet/signs/oldfolder/"
  - "[GAME]/media_soviet/signs/stale.ini"
```

| Key | Meaning |
|---|---|
| `item` | The workshop item this list belongs to — the **origin**. Numeric ID. |
| `copy` | A list of `src` / `dst` pairs. Optional if `remove` is present. |
| `remove` | A list of destination paths to take away. Optional if `copy` is present. |

A list needs an `item` and at least one operation.

### `src` — where files come from

`src` is always relative to the origin item's own workshop folder, and
cannot reach outside it.

| `src` | Copies |
|---|---|
| `filename.ini` | That one file |
| `foldername/` | That folder and everything under it, folder included |
| `*` | Everything in the origin folder except `workshopconfig.ini` |

The `workshopconfig.ini` exclusion is fixed — it is Steam's own metadata
for the item and has no business being copied anywhere.

### `dst` — where they go

`dst` must start with one of two placeholders:

| Placeholder | Resolves to |
|---|---|
| `[GAME]/...` | Your game install folder |
| `[WORKSHOP]/{id}/...` | Workshop item `{id}`'s own folder |

Copying into another item's folder is deliberate — it is how an import list
patches a different mod. Quote any `dst` in YAML, because a bare `[...]`
is a YAML list.

`remove` entries use the same two placeholders. They are destination paths,
not origin-relative ones.

## Running one

```
> wrsrcli import mylist.yaml

Copied 14 file(s); removed 1 target(s).
Backed up 3 original(s) to C:\Users\you\AppData\Roaming\wrsrcli\backups\3780739284\20260920-003300
```

If the origin item is not installed locally, `wrsrcli` offers to fetch it
through SteamCMD first — see `wrsrcli steamcmd --install` in
[Use.md](Use.md).

A `remove` target that is already gone is reported as a warning and does
not stop the run.

### Conflicts

If two `copy` entries end up writing different source files to the same
destination — most often a broad `*` overlapping a specific named file —
`wrsrcli` stops and asks, before writing anything at all:

```
Conflict: 2 sources map to D:\...\media_soviet\signs\signscript.txt
   1. signscript.txt                 - modified 2026-08-12 04:23
   2. signscript.txt                 - modified 2026-07-30 11:05

Please select which to copy (or press ENTER to skip this file):
```

Press ENTER to leave that one destination alone and carry on with the rest.

The whole run is planned and every conflict settled before the first file
is written, so you are never part-way through an import when a question
arrives.

## Undoing an import

Each `import` run is one **generation**, stored in its own timestamped
folder. If several imports have affected the same files you are shown the
list and asked which generation you want.

### `wrsrcli restore {steamid}`

Repairs damage done **to** an item. Give it the ID of the item whose files
were overwritten or removed, and the backed-up originals go back.

Use `wrsrcli restore vanilla` for base game files, which are recorded under
that name rather than an item ID.

### `wrsrcli rollback {steamid}`

Undoes what an item's import list did **elsewhere**. Give it the origin ID
— the `item:` from the list — and everything that run overwrote or removed,
wherever it landed, is put back.

The distinction is which end you know: `restore` if you know what got
broken, `rollback` if you know what broke it.

Note that rollback returns overwritten and removed files. Files the import
*created* where nothing existed are not tracked, so they are left in place;
delete those yourself if you want them gone.

## Keeping imports applied

Steam does not know about any of this. When it updates a workshop item, or
when you verify the game's files, it can quietly put back exactly the files
an import replaced.

### `wrsrcli manual-check`

Compares what the backup store recorded against the current state of your
install and flags anything that looks reverted:

```
> wrsrcli manual-check
2 tracked change(s) may have been reverted:

  D:\...\media_soviet\signs\signscript.txt
    origin 3780739284 -> vanilla: modified 2026-09-19 22:14, after this import

Run `wrsrcli manual-rerun` to re-apply the tracked import lists.
```

For a destination inside a workshop item, the check is that item's Steam
update time. For a game file there is no such record, so the file's own
modification time is used — which means anything that touches that file,
including you editing it on purpose, will show up here. Treat game-file
hits as "worth a look", not as proof.

### `wrsrcli manual-rerun`

Re-applies the most recent import list for every origin item that has ever
been imported. `wrsrcli` keeps its own verbatim copy of each list when you
run it, so this works even if you have since moved, edited or deleted the
file you originally pointed at.

A rerun goes through exactly the same path as a fresh `import` — same
conflict prompts, same backup-before-write — so re-applying is as
reversible as applying was.

## Writing a list for others

- Give `item` the ID of the asset the list belongs to, so `rollback` and
  `manual-rerun` can find it.
- Prefer naming files explicitly over `*`. It documents what the asset
  actually needs and avoids conflict prompts your users then have to answer.
- Quote every `dst` and `remove` entry.
- Test it on your own install, then run `wrsrcli rollback {item}` and check
  you are genuinely back where you started.

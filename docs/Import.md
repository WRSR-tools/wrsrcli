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
version: 1

items:
  - item: 3780739284
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
| `version` | The markup version the file is written to. Required, and first. |
| `items` | The list of items the file describes — one entry each, even for one item. |
| `item` | The workshop item an entry belongs to — the **origin**. Numeric ID. |
| `copy` | A list of `src` / `dst` pairs. Optional if `remove` is present. |
| `remove` | A list of destination paths to take away. Optional if `copy` is present. |
| `depends-mandatory` | Items this one needs. Fetched automatically. |
| `depends-optional` | Items this one benefits from. You are asked about each. |

Every entry needs an `item` and at least one thing to do.

This is **WMLS version 1**. A list written to the older markup — no
`version:` line, a single `item:` at the top level — still works, but
`wrsrcli` will tell you it is on borrowed time. Adding `version: 1` and
indenting the item under `items:` is the whole migration.

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

`*` is not a wildcard you can put inside a path. It means the origin
folder and nothing else, so `src: "signs/*"` is rejected — write
`src: "signs/"` instead.

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

### Dependencies

Some assets only work alongside others. An entry can say so:

```yaml
    depends-mandatory:
      - item: 3621284903
    depends-optional:
      - item: 3111111111
        message: "Adds night lighting for these signs"
```

Anything already in your workshop folder is left alone. Anything missing
is subscribed to through Steam — mandatory ones without asking, since the
item does not work without them, and optional ones one at a time:

```
Item 3780739284 suggests item 3111111111:
   Adds night lighting for these signs
Press ENTER to download it, or type anything else to skip:
```

That is why `message` is required on an optional dependency — it is the
only thing you have to go on when deciding.

Dependencies are **downloaded, not applied**. If a dependency has its own
import list, run that list yourself.

### Several items in one file

`items:` can hold as many entries as you like:

```yaml
version: 1

items:
  - item: 3780739284
    copy:
      - src: "*"
        dst: "[GAME]/media_soviet/paths/"

  - item: 3621284903
    copy:
      - src: media_soviet/paths/
        dst: "[GAME]/media_soviet/paths/"
```

They are applied in the order written, and each one is its own backup
generation — exactly as if you had imported them from separate files. So
`restore`, `rollback` and `manual-rerun` all work per item, not per file.
An item may only appear once in a file; put all of its operations in the
one entry.

## Running one

```
> wrsrcli import mylist.yaml

=== item 3780739284 (1 of 2) ===

Copied 14 file(s); removed 1 target(s).
Backed up 3 original(s) to C:\Users\you\AppData\Roaming\wrsrcli\backups\3780739284\20260920-003300
```

If the origin item is not installed locally, `wrsrcli` offers to fetch it
through Steam first: wrsrcli subscribes to it and waits for Steam to
finish installing it.

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

For a file describing several items, each origin is replayed on its own —
the file is not re-applied whole once per item it contains.

A rerun goes through exactly the same path as a fresh `import` — same
conflict prompts, same backup-before-write — so re-applying is as
reversible as applying was.

## Writing a list for others

- Start the file with `version: 1`.
- Give each `item` the ID of the asset that entry belongs to, so `rollback`
  and `manual-rerun` can find it.
- Say what an optional dependency is *for* in its `message`. Your users are
  deciding on that sentence alone.
- Prefer naming files explicitly over `*`. It documents what the asset
  actually needs and avoids conflict prompts your users then have to answer.
- Quote every `dst` and `remove` entry.
- Test it on your own install, then run `wrsrcli rollback {item}` and check
  you are genuinely back where you started.

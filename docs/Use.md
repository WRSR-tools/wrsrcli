# Using wrsrcli

Every command is `wrsrcli {command}`. Run `wrsrcli` on its own, or
`wrsrcli --help`, for the list; `wrsrcli {command} --help` shows one
command's options.

The help lists command names and headings in rusty red where your console
supports it. Set `NO_COLOR=1` to turn that off, or redirect the output to a
file, which is always plain text.

This page covers everything except import lists, which have their own
guide: [Import.md](Import.md).

## Setup

### `wrsrcli path`

With no options, prints the paths currently stored:

```
> wrsrcli path
Game path:     D:\SteamLibrary\steamapps\common\SovietRepublic
Workshop path: D:\SteamLibrary\steamapps\workshop\content\784150
```

| Option | Effect |
|---|---|
| `-a`, `--auto-detect` | Find both paths from the Windows registry and store them |
| `-g`, `--game "{path}"` | Set the game install folder explicitly |
| `-w`, `--workshop "{path}"` | Set the workshop content folder explicitly |

Autodetection reads Steam's install path from the registry, looks through
`libraryfolders.vdf` for the library holding app 784150, and takes the game
folder name from that library's `appmanifest_784150.acf` rather than
assuming it — so a renamed install folder still resolves.

You do not have to run this first. The first command that needs a path will
autodetect and store it for you. Run it explicitly when autodetection gets
it wrong, or when you want to see what was found.

An explicit `-g`/`-w` always wins over a detected value, including when
given in the same invocation as `-a`.

### `wrsrcli api {key}`

Stores a [Steam Web API key](https://steamcommunity.com/dev/apikey), which
`output-table` uses to fetch author names, posted dates and file sizes, and
`scan` uses to find out which items depend on which.

```
wrsrcli api 0123456789ABCDEF0123456789ABCDEF
```

The key is written to `%APPDATA%\wrsrcli\config.json`. It is never printed
back to you, never written into the HTML table, and never included in an
error message.

| Command | Effect |
|---|---|
| `wrsrcli api` | Say whether a key is stored, without showing it |
| `wrsrcli api {key}` | Store a key, replacing any existing one |
| `wrsrcli api -r` / `--remove` | Delete the stored key |

Everything except the three API-only columns works without a key.

## Inventory

### `wrsrcli scan`

Reads Steam's `appworkshop_784150.acf` and your workshop folder, and writes
an inventory to `%APPDATA%\wrsrcli\manifest.json`.

```
> wrsrcli scan
Scanned 21 installed item(s) from D:\...\workshop\content\784150
16 item(s) declare dependencies; 1 not installed: 3773169177
Manifest written to C:\Users\you\AppData\Roaming\wrsrcli\manifest.json
```

Only items actually **downloaded** are inventoried. Steam's `.acf` also
lists items you are subscribed to but which have not been fetched yet;
those are skipped.

Every workshop download ships a `workshopconfig.ini`, so if one is missing
the item was changed locally. That item is still listed, with its owner and
type left empty, and a warning is printed naming it.

**Dependencies.** Many workshop items require another item to work — a mod
loader, say. If you have set an API key, `scan` asks Steam which items each
of yours requires, records them in the manifest, and tells you about any
that are not installed. In the example above, four mods need TesmioLoader
and it is not there; those mods are unlikely to be working in-game. Steam
does not warn you about this anywhere, and nothing local shows it.

Without a key, `scan` works exactly as it always did and says that
dependencies were not checked. If the API call fails, you get a warning and
the rest of the manifest is still written.

Re-run `scan` whenever you subscribe to or unsubscribe from anything.

### `wrsrcli output-table`

Turns the manifest into `WRSR Assets.html` — a single self-contained file
with search, a type filter and sortable columns.

```
> wrsrcli output-table
Please enter path to save folder, or press ENTER to use Documents. The filename will be WRSR Assets.html:
```

Press ENTER for your Documents folder, or type a path. If a
`WRSR Assets.html` is already there you are asked whether to overwrite it
or to save alongside it with a timestamp in the name.

The file embeds its own data and styling and loads nothing from the
internet, so it keeps working offline, forever, and can be copied anywhere.

Columns without an API key: Item ID, Name, Type, Tags, Owner ID, Updated.
With a key, Owner ID is replaced by the author's display name and Posted
and Size are added.

Item IDs link to the workshop page, and authors to their Steam profile.
Both open in a new tab. The links are the only thing in the file that
points outwards, and nothing is loaded from the internet to display it.

Any item with dependencies gets a ▸ button at the start of its row. Open it
to see what that item needs:

```
DEPENDENCIES
- 3787969749 Republic Mod Loader [1.1.1.9] (UltimateUniverse) (OK)
- 3773169177 TesmioLoader v. b0.3.6 (for WRSR 1.1.1.9) (Tesmio) (Not installed)
```

`OK` means you have it. **Not installed** is highlighted — that item is
missing and whatever needs it probably will not work. The IDs and creators
in the list are links too, so a missing dependency is one click from the
page you would install it from.

Dependencies come from the manifest, so they still appear when you build a
table without a key — as long as the scan that wrote the manifest had one.

**Status at a glance.** Two panels sit above the table. Each says its state
in its own heading, so you can read them without opening anything:

- **Dependencies (OK)** in green, or **Dependencies (Dependencies
  missing)** in red, listing what is missing.
- **Asset status (OK)** in green, or **Asset status (Update needed)** in
  red, listing items the workshop has a newer version of.

A green panel is closed — there is nothing inside worth reading. A red one
is already open, and tells you to run `wrsrcli update`.

Both panels work **without** an API key. Steam itself records the newest
version it knows of for each item, so "is this out of date" is answered
from your own Steam files. With a key set, the check is made live against
the workshop instead; without one, the panel says it checked Steam's own
record as of its last sync. If neither can answer — an old manifest, or an
item only `update` put there — the panel is left out rather than claiming
everything is current when it cannot tell.

The **Updated** column is the version *you have installed*, not the latest
published. That is the point of the Asset status panel: if the two differ,
the panel says so rather than the column quietly showing you a version you
do not have.

### `wrsrcli update`

Downloads what the table says is needed — missing dependencies, and items
with a newer version on the workshop. Works with or without an API key.

```
> wrsrcli update
Missing dependencies (1):
   - 3773169177 TesmioLoader v. b0.3.6 (for WRSR 1.1.1.9) — required by 3773771138, 3774939545, 3779449644, 3779842468

1 item(s) will be downloaded through SteamCMD into your workshop folder.
Press ENTER to download, or anything else to cancel:
```

Nothing is downloaded until you press ENTER; anything else cancels. You
need SteamCMD — run `wrsrcli steamcmd --install` first if you have not.

Files go into your workshop folder, where the game looks for them. If an
item is being **replaced** because it is out of date, the old copy is
backed up first, so `wrsrcli rollback {steamid}` puts it back.

Re-run `wrsrcli scan` afterwards so the manifest catches up.

> **Steam does not know about items downloaded this way.** It will not keep
> them updated, and verifying the game's files may remove them. Subscribing
> to an item in Steam is the durable fix; `update` is for getting a
> dependency in place now, or when subscribing is not an option.

If Steam's API is unreachable or rejects your key, `output-table` says so
and falls back to the local-only table rather than failing — you still get
a usable file.

Run `scan` first; `output-table` reads the manifest and will not build one
for you.

## Imports

These five commands are covered in full in [Import.md](Import.md).

| Command | What it does |
|---|---|
| `wrsrcli import {path}` | Apply a YAML import list, backing up anything it overwrites or removes |
| `wrsrcli restore {steamid}` | Put back files that imports overwrote **on** this item |
| `wrsrcli rollback {steamid}` | Undo what this item's import did **elsewhere** |
| `wrsrcli manual-check` | Flag tracked imports that Steam looks to have reverted |
| `wrsrcli manual-rerun` | Re-apply every tracked import list |

## SteamCMD

### `wrsrcli steamcmd --install`

Installs SteamCMD, which `import` uses to fetch an origin item you are not
subscribed to. Default location is `[STEAMPATH]/steamcmd`; `-p "{path}"`
puts it elsewhere.

This is the only part of `wrsrcli` that downloads and runs third-party
code, so it always asks first:

```
Press ENTER to automatically download and install steamcmd from Valve. If you prefer to download and install yourself, please open this link:
   https://developer.valvesoftware.com/wiki/SteamCMD
```

**Only pressing ENTER proceeds.** Typing anything at all cancels and
nothing is downloaded. Workshop downloads through SteamCMD are made
anonymously — `wrsrcli` never asks for, stores or passes on your Steam
credentials. An item that requires an account will fail here, and you will
need to fetch it through Steam yourself.

If SteamCMD is already installed at the target path, the command says so
and leaves it alone.

## Managing the tool itself

| Command | What it does |
|---|---|
| `wrsrcli install` | Copy the standalone `.exe` onto your PATH — see [Install.md](Install.md) |
| `wrsrcli uninstall` | Remove it again, leaving your settings and backups alone |
| `wrsrcli open-web` | Open the project website in your default browser |
| `wrsrcli --version` | Print the version |

### `wrsrcli open-web`

Opens <https://wrsr-tools.github.io/> in whichever browser Windows is set to
use. The URL is printed before the browser opens, so you can copy it if
nothing comes up.

## When something goes wrong

`wrsrcli` reports problems as a single line starting `wrsrcli:` rather than
a Python traceback. If you ever see a traceback, that is a bug worth
reporting.

Common ones:

| Message | What to do |
|---|---|
| `manifest.json not found` | Run `wrsrcli scan` first |
| `app 784150 is not installed in any Steam library` | Set the paths by hand with `wrsrcli path -g`/`-w` |
| `Steam is not registered on this machine` | Steam has never run for this Windows user; set paths by hand |
| `{path} does not exist — no workshop items are downloaded` | Subscribe to something in Steam and let it download |

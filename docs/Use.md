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
`output-table` uses to fetch author names, posted dates and file sizes.

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
Manifest written to C:\Users\you\AppData\Roaming\wrsrcli\manifest.json
```

Only items actually **downloaded** are inventoried. Steam's `.acf` also
lists items you are subscribed to but which have not been fetched yet;
those are skipped.

Every workshop download ships a `workshopconfig.ini`, so if one is missing
the item was changed locally. That item is still listed, with its owner and
type left empty, and a warning is printed naming it.

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

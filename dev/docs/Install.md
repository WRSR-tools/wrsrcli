# Installing wrsrcli

`wrsrcli` is a Windows-only command-line tool. There are two ways to get it:
the standalone executable (no Python needed) or a `pip` install from source.

## The standalone executable

1. Download `wrsrcli-windows-amd64.exe` from the
   [latest release](https://github.com/WRSR-tools/wrsrcli/releases/latest).
2. Double-click it.

Because it is a command-line tool, it is not much use sitting in your
Downloads folder, so double-clicking it opens the installer:

```
wrsrcli dev - Workshop Manager for Workers and Resources: Soviet Republic
================================================================================
This is the installer for the wrsrcli - a command line tool to manage workshop
assets for Workers and Resources: Soviet Republic.

For more information on how to use this tool, please visit:
   https://wrsr-tools.github.io

   Press ENTER to install...
```

Press ENTER and it installs itself to
`%LOCALAPPDATA%\Programs\wrsrcli` and adds that folder to your PATH,
telling you as it does both. Then **open a new terminal window** — PATH
changes only reach shells started afterwards — and run:

```
wrsrcli --help
```

**Only ENTER installs.** Type anything at all before pressing ENTER and
nothing is installed, the same rule `wrsrcli steamcmd --install` follows.
The executable works fine run directly from wherever it sits; it only needs
installing so that `wrsrcli` resolves from any folder.

### Installing from a terminal instead

If you already have a terminal open in the folder you downloaded it to:

```
.\wrsrcli-windows-amd64.exe install
```

To put it somewhere other than the default:

```
.\wrsrcli-windows-amd64.exe install -p "D:\Tools\wrsrcli"
```

`install` is idempotent — running it twice will not add a duplicate PATH
entry.

### What `install` actually changes

- Copies the executable to `%LOCALAPPDATA%\Programs\wrsrcli\wrsrcli.exe`
  (or to your `-p` path).
- Appends that one folder to the **user** PATH, under `HKCU\Environment`.

That is all. The machine-wide PATH is never touched, no admin rights are
required, no services or registry run-keys are created, and nothing is
installed for other users of the PC.

If adding the folder would push your PATH past Windows' 32767-character
limit, `wrsrcli` refuses rather than writing a truncated PATH — install
somewhere with a shorter path, or tidy your PATH first.

### Uninstalling

```
wrsrcli uninstall
```

This removes the installed `wrsrcli.exe` and takes its folder back off your
PATH. If you passed `-p` when installing, pass the same `-p` here.

Windows will not let a running program delete itself, so if you run
`uninstall` from the installed copy, the PATH entry is removed and you are
told to delete the one remaining `.exe` by hand.

Your settings, manifest and **all your backups** live in
`%APPDATA%\wrsrcli\` and are deliberately left alone, so uninstalling can
never cost you a file an import overwrote. Delete that folder yourself if
you really want everything gone.

## From source, with pip

Requires Python 3.12 or newer.

```
git clone https://github.com/WRSR-tools/wrsrcli.git
cd wrsrcli
pip install .
```

This puts a `wrsrcli` script in that environment's `Scripts` folder, which
pip already keeps on your PATH — so `wrsrcli install` does not apply here
and will tell you so if you try it.

You can also run it without installing:

```
python -m wrsrcli --help
```

## Where wrsrcli keeps its files

Nothing is stored next to the executable or in the repository. Everything
lives in `%APPDATA%\wrsrcli\`:

| File or folder  | What it holds                                       |
|-----------------|-----------------------------------------------------|
| `config.json`   | Your Steam Web API key and your game/workshop paths |
| `manifest.json` | The asset inventory that `scan` writes              |
| `backups.json`  | A record of every file an import overwrote or removed |
| `backups\`      | The backed-up files themselves                      |
| `imports.json`  | Which import lists have been run                    |
| `imports\`      | A verbatim copy of each import list that was run    |

## First-time setup

Once installed, point `wrsrcli` at your game:

```
wrsrcli path --auto-detect
```

This reads the Steam install path from the registry, finds which Steam
library holds app 784150, and stores both the game folder and the workshop
content folder. If your setup defeats autodetection, set them by hand:

```
wrsrcli path -g "D:\SteamLibrary\steamapps\common\SovietRepublic"
wrsrcli path -w "D:\SteamLibrary\steamapps\workshop\content\784150"
```

Then carry on with [Use.md](Use.md).

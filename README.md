# wrsrcli

A Windows command-line tool for managing Steam Workshop assets for
*Workers & Resources: Soviet Republic*.

It inventories what you have subscribed to, turns that into a searchable
offline HTML table, and applies user-authored **import lists** — small YAML
files that copy or remove files into the game or into another mod's folder,
which is how a good many WRSR assets are meant to be installed.

Nothing is ever hard-deleted. Every file an import overwrites or removes is
backed up first, and `restore` / `rollback` put it back.

## Install

Download `wrsrcli-windows-amd64.exe` from the
[latest release](https://github.com/WRSR-tools/wrsrcli/releases/latest) and
double-click it — it offers to install itself onto your PATH. No Python and
no administrator rights are needed.

Full instructions, including the `pip` route and how to uninstall, are in
[docs/Install.md](docs/Install.md).

## Use

```
wrsrcli path --auto-detect     find your game and workshop folders
wrsrcli scan                   build the asset manifest
wrsrcli output-table           write a searchable WRSR Assets.html
wrsrcli update                 subscribe to missing deps and updates
wrsrcli import mylist.yaml     apply an import list, with backups
```

Every command is documented in [docs/Use.md](docs/Use.md), and the
import-list format has its own guide in [docs/Import.md](docs/Import.md).

## Requirements

Windows, with Steam and *Workers & Resources: Soviet Republic* installed.
The standalone `.exe` needs nothing else; running from source needs Python
3.12 or newer.

## Development

`AGENTS.md` holds the working rules for this repository. The specification,
execution plan, progress log and decision records live under `dev/`, and
`dev/REPO-STRUCTURE.md` explains what each of those is.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

One bundled file is **not** covered by it:
`wrsrcli/vendor/steamworks/steam_api64.dll` is Valve Corporation's
Steamworks SDK Redistributable, redistributed under the
[Steamworks SDK Access Agreement](https://partner.steamgames.com/documentation/sdk_access_agreement).
It is what lets wrsrcli subscribe to workshop items on your behalf; delete
it and wrsrcli opens the item's Steam page for you to click Subscribe
instead. See [NOTICE](NOTICE) and
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

wrsrcli is not affiliated with or endorsed by Valve Corporation.

# WMLS - WRSRCLI Markup Language Standard

`wrsrcli` can import YAML files to perform the following functions:

- Fetch and present metadata about downloaded files
- Fetch and install files not yet downloaded
- Overwrite and remove files 
- Restore backups

This standard describes the keys and values in use and expected future implementation.

| | |  
|---|---|  
|**CANONICAL WEB ADDRESS**|https://wrsr-tools.github.io/#pages/wmls/standard.md|
|**CURRENT VERSION**|Version 1 (`v1`)|  
|**CURRENT VERSION DATE**|20 September 2026|
|**LICENCE**|[Apache 2](pages/wmls/licence.md)|

## 0. Basic overview

WMLS files are YAML files. YAML rules apply. This standard defines valid keys and values to help users and developers create proper import files for `wrsrcli`.

This standard and the tool that uses it are licenced under the Apache 2 licence. You are free to use any part of the documentation or code in your own project. Development happens on [GitHub](https://github.com/wrsr-tools/wrsrcli) and are documented on [GitHub Pages](https://wrsr-tools.github.io/).

## 1. Version

`wrsrcli` parses according to the rules in WMLS. Each released version supports the one before it. Each file **must** declare a version as the first line in their file:

```yaml
version: 1
```

## 2. Current standard - `v1`

### Item identifier

Each WMLS file targets defined workshop assets. `v1` accepts one or more items per file. Each item starts with `item: {steamid}`, where `{steamid}` is the asset's numerical identifier in the Steam workshop (visible to users as the last part of an asset's web address: `https://steamcommunity.com/sharedfiles/filedetails/?id=NNNNNNNNNN`).

Items are declared under `items:`, one list entry per item:

```yaml
version: 1

items:
  - item: NNNNNNNNNN
```

A file with a single item still uses `items:`, with one entry in the list.

#### Item keys

Under each item, the following keys can be defined:

##### `copy:`

`copy:` instructs `wrsrcli` to copy the defined files in the workshop file to another workshop folder or a folder in the game root. `copy:` requires a source (`src`) and a destination (`dst`).

To copy the content of the folder `signs` in workshop folder `NNNNNNNNNN` and move to `signs` in `media_soviet`, first declare the item and then the action:

```yaml
items:
  - item: NNNNNNNNNN
```

Then you declare the action:
```yaml
    copy:
      - src: signs/
        dst: "[GAME]/media_soviet/signs/"
```

To copy only an individual file, specify it as the source, and specify the folder in which it is to be placed:

```yaml
    copy:
      - src: signscript.txt
        dst: "[GAME]/media_soviet/signs/"
```

The destination can also be another workshop folder. For example, to replace a file in another workshop folder (e.g., because to update an asset's parameters), you can do the following to replace `building.ini` in the destination item's root folder:

```yaml
    copy:
      - src: patch/building.ini
        dst: "[WORKSHOP]/3621284903/"
```

To copy everything in the origin item's own folder (except `workshopconfig.ini`, which is Steam's own metadata and is never copied), use `*`:

```yaml
    copy:
      - src: "*"
        dst: "[GAME]/media_soviet/paths/"
```

`*` always means "everything in the origin item's root folder." It does not act as a wildcard inside a sub-path — `src: "signs/*"` is not valid; use `src: "signs/"` to copy that folder's contents instead.

##### `remove:`

To remove a specified folder or file, you declare `remove:` and list the folders or files to be removed:

```yaml
    remove:
      - "[GAME]/media_soviet/signs/oldfolder/"
      - "[GAME]/media_soviet/signs/stale.ini"
```

##### `depends-mandatory:`

Mandatory dependencies which will be automatically downloaded. Each is defined by an `item` key:

```yaml
    depends-mandatory:
      - item: XXXXXXXXXX
```

##### `depends-optional:`

Optional dependencies. These can be used where a dependency is not necessary but would otherwise enhance gameplay. Use `item` to define the item to download, and `message` to present a message to the user when asking if the item should be downloaded.

```yaml
    depends-optional:
      - item: ZZZZZZZZZZ
        message: "Short message to user which is shown when the user is asked to decide to whether to install or not"
```

#### Combined example

All keys can be combined, and a file can describe multiple items:

```yaml
version: 1

items:
  - item: NNNNNNNNNN
    copy:
      - src: "*"
        dst: "[GAME]/media_soviet/paths/"
    remove:
      - "[GAME]/media_soviet/paths/filen.ame"

  - item: YYYYYYYYYY
    copy:
      - src: "media_soviet/paths/"
        dst: "[GAME]/media_soviet/paths/"
    remove:
      - "[GAME]/media_soviet/paths/filen.ame"
    depends-mandatory:
      - item: XXXXXXXXXX
    depends-optional:
      - item: ZZZZZZZZZZ
        message: "Short message to user which is shown when the user is asked to decide to whether to install or not"
```

### Variables

WMLS specifies two variables:

- `[GAME]`: This variable resolves to your game install folder (often `C:\Program Files (x86)\Steam\steamapps\common\SovietRepublic\`).
- `[WORKSHOP]`: This variable resolves to your workshop root folder (often `C:\Program Files (x86)\Steam\steamapps\workshop\content\784150`).

## Roadmap

Intended additions include:

- **Conditional copying/removing**: The ability to specify copying/removing individual files or folders, presented to the user along with a message explaining what is going on.
- **List repos**: Essentially a folder containing various lists, searchable in `wrsrcli`. This would require support for metadata.



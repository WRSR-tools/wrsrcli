# Third-party notices

wrsrcli is licensed under the Apache License 2.0 ([LICENSE](LICENSE)), with
one exception, described here and summarised in [NOTICE](NOTICE).

## Steamworks SDK Redistributable

| | |
|---|---|
| **File** | `wrsrcli/vendor/steamworks/steam_api64.dll` |
| **Copyright** | © 1996–2026, Valve Corporation. All rights reserved. |
| **Source** | Steamworks SDK v1.65, `redistributable_bin/win64/` |
| **Size** | 319,128 bytes |
| **SHA-256** | `e6d9bafb9a41e42fba7b21553db49f8719027af3f0deb23ff86cfc44d60e776d` |
| **Licence** | [Steamworks SDK Access Agreement](https://partner.steamgames.com/documentation/sdk_access_agreement) |

**This file is not covered by the Apache License 2.0.** It is Valve
Corporation's software, redistributed under section 1.1(b) of the Steamworks
SDK Access Agreement, which permits reproducing and distributing the SDK's
`redistributable_bin` contents along with the software built against them.

The agreement's text is not reproduced here. Read it at the link above.

### Why it is here

`wrsrcli update` and `wrsrcli import` can subscribe to Steam Workshop items
on the user's behalf, through `ISteamUGC::SubscribeItem`. A subscription is
what makes Steam install an item and keep it updated, and it is the only
route that leaves Steam's own records correct. Section 2.4 of the agreement
requires that software interacting with Steamworks Services do so through
the API provided by the SDK Redistributables rather than by communicating
with those services directly, so this library is the sanctioned way to do
it, not a shortcut around one.

Everything else in wrsrcli works without it. Where it is absent or fails to
load, the affected commands open the item's Steam page instead, and the user
subscribes with one click.

### If you fork or redistribute wrsrcli

The Apache License over the rest of this work grants you nothing in this
file, and section 6.2 of the Steamworks agreement bars assignment. Your
right to redistribute it rests on your own acceptance of the Steamworks SDK
Access Agreement, which you accept by downloading the SDK from Valve.

If you would rather not rely on that, delete the file. wrsrcli detects its
absence and degrades as described above; nothing else changes.

### Trademarks

Section 2.3 grants no rights in Valve's trademarks or trade names. wrsrcli
is not affiliated with, endorsed by, or a partner of Valve Corporation.
"Steam", "Steamworks" and "Steam Workshop" are used only to describe what
this tool interoperates with.

# versions/

One file per release, `vX.Y.Z.txt`, written by the release workflow when a
tag is pushed. `wrsrcli --version` fetches the file naming its own build and
prints the line it finds.

The newest release says:

```
vX.Y.Z - released on 1 January 2026. This is the latest version.
```

Every older one is rewritten, keeping its own version and release date:

```
vX.Y.Z - released on 1 January 2026. This file is outdated. Please run wrsrcli upgrade to download the latest version.
```

**These files are generated. Do not edit them by hand** — the next release
overwrites them.

The point of a file per version, rather than asking GitHub what the latest
release is, is that a build only needs to fetch the one file named after
itself: a single small request, no API, no rate limit, no JSON, and no way
for an old build to misread a newer release's metadata. The wording lives
here rather than in the tool, so what a released build says about itself can
be corrected without shipping a new build.

`wrsrcli upgrade` does use the releases API, because it needs the asset's
download URL and there is no way to know that in advance.

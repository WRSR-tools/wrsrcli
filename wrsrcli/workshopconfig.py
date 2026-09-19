"""Parser for `workshopconfig.ini` — Valve's line-oriented `$KEY value` format.

Not real INI, and not the KeyValues format in `vdf.py` (SPEC.md 2.2). Rules
confirmed against the 20 real items in the local workshop folder:

- One `$KEY value` per line; `$END` terminates the file.
- Any key may repeat (`$TAGS`, `$OBJECT_BUILDING` do in practice), so every
  key maps to a list of values and callers pick what they need.
- Keys are open-ended: items in the local folder carry `$ADD_CUSTOM_SOUNDS2D`
  and `$ADD_CUSTOM_SOUNDS3D`, which SPEC.md does not list. No whitelist.
- A value may be quoted and span many lines (`$ITEM_DESC`). Descriptions
  contain mid-line `"` characters, so a quoted value ends at a `"` that ends
  a line — not at the first `"` found. Contents are taken literally;
  backslashes are not escape sequences here.
- Files are UTF-8 with no BOM.
"""

from .errors import WrsrcliError

END = "$END"


def _closes(line):
    """True if `line` ends a quoted value (a `"` at end of line)."""
    return line.rstrip().endswith('"')


def loads(text):
    """Parse workshopconfig.ini text into {key: [value, ...]}."""
    record = {}
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        index += 1

        stripped = line.strip()
        if not stripped.startswith("$"):
            continue
        if stripped == END:
            break

        parts = stripped.split(None, 1)
        key = parts[0]
        rest = parts[1] if len(parts) > 1 else ""

        if rest.startswith('"'):
            body = rest[1:]
            if _closes(body) and body.strip() != "":
                value = body.rstrip()[:-1]
            else:
                # Multi-line quoted value: take following lines verbatim so
                # the description's own formatting survives.
                chunks = [body]
                while index < len(lines):
                    nxt = lines[index]
                    index += 1
                    if _closes(nxt):
                        chunks.append(nxt.rstrip()[:-1])
                        break
                    chunks.append(nxt)
                else:
                    raise WrsrcliError(
                        f"{key}: quoted value is never closed before end of file."
                    )
                value = "\n".join(chunks)
        else:
            value = rest

        record.setdefault(key, []).append(value)

    return record


def load(path):
    """Parse a workshopconfig.ini file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise WrsrcliError(f"could not read {path}: {exc}") from exc
    return loads(text)


def first(record, key, default=None):
    """The first value for `key`, or `default` if absent."""
    values = record.get(key)
    return values[0] if values else default

"""Parser for Valve's KeyValues text format.

Used by `libraryfolders.vdf`, `appmanifest_{appid}.acf` and
`appworkshop_784150.acf` — all the same format despite the differing
extensions. Handles the subset Steam actually writes: quoted keys and
values, nested brace-delimited blocks, and `//` line comments.

Note this is *not* the same format as `workshopconfig.ini`, which uses
Valve's other, line-oriented `$KEY value` syntax (see SPEC.md 2.2).
"""

from .errors import WrsrcliError

_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}


def _tokenize(text):
    i = 0
    length = len(text)
    while i < length:
        char = text[i]

        if char in " \t\r\n":
            i += 1
            continue

        if char == "/" and i + 1 < length and text[i + 1] == "/":
            newline = text.find("\n", i)
            i = length if newline == -1 else newline + 1
            continue

        if char in "{}":
            yield char
            i += 1
            continue

        if char == '"':
            i += 1
            chunks = []
            while i < length and text[i] != '"':
                if text[i] == "\\" and i + 1 < length:
                    chunks.append(_ESCAPES.get(text[i + 1], text[i + 1]))
                    i += 2
                else:
                    chunks.append(text[i])
                    i += 1
            if i >= length:
                raise WrsrcliError("malformed KeyValues data: unterminated string")
            i += 1
            yield '"' + "".join(chunks)
            continue

        # Unquoted token, terminated by whitespace or a brace.
        start = i
        while i < length and text[i] not in ' \t\r\n{}"':
            i += 1
        yield '"' + text[start:i]


def _parse_block(tokens):
    """Parse tokens up to the matching '}' (or end of input at top level)."""
    result = {}
    for token in tokens:
        if token == "}":
            return result
        if token == "{":
            raise WrsrcliError("malformed KeyValues data: unexpected '{'")

        key = token[1:]
        try:
            value_token = next(tokens)
        except StopIteration:
            raise WrsrcliError(
                f"malformed KeyValues data: key {key!r} has no value"
            ) from None

        if value_token == "{":
            result[key] = _parse_block(tokens)
        elif value_token == "}":
            raise WrsrcliError(
                f"malformed KeyValues data: key {key!r} has no value"
            )
        else:
            result[key] = value_token[1:]

    return result


def lookup(mapping, name):
    """Case-insensitive key lookup — Valve's capitalization has varied."""
    if not isinstance(mapping, dict):
        return None
    for key, value in mapping.items():
        if key.lower() == name.lower():
            return value
    return None


def loads(text):
    """Parse KeyValues text into nested dicts."""
    return _parse_block(_tokenize(text))


def load(path):
    """Parse a KeyValues file. Valve writes these as UTF-8."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise WrsrcliError(f"could not read {path}: {exc}") from exc
    return loads(text)

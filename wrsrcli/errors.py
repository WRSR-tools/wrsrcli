"""Error type for conditions the user should see as a message, not a traceback."""


class WrsrcliError(Exception):
    """A failure wrsrcli can explain: missing path, unreadable file, bad input."""

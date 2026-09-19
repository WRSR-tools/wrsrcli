"""PyInstaller entry point.

`pyproject.toml`'s `[project.scripts]` covers `pip install`, but PyInstaller
needs a real script to freeze. This is that script, and nothing else should
import it — `wrsrcli/__main__.py` remains the entry for `python -m wrsrcli`.
"""

import sys

from wrsrcli.cli import main

if __name__ == "__main__":
    sys.exit(main())

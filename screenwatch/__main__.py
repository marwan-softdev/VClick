"""Command-line entry point: ``python -m screenwatch``.

The actual logic lives in :mod:`screenwatch.cli` -- see the note there for
why it isn't here.
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())

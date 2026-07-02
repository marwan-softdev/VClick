"""Command-line entry point: ``python -m screenwatch``."""

from __future__ import annotations

import argparse
import sys

from . import __app_name__, __version__


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="screenwatch",
        description=f"{__app_name__} — watch a screen area and auto-click when it changes.",
    )
    parser.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    parser.add_argument("--config", metavar="PATH", help="path to an alternate config file")
    parser.add_argument(
        "--check",
        action="store_true",
        help="print environment/backend diagnostics and exit (no GUI)",
    )
    args = parser.parse_args(argv)

    if args.check:
        return _check()

    from .config import Config
    from .gui import run

    config = Config.load(args.config) if args.config else Config.load()
    try:
        run(config)
    except Exception as exc:  # noqa: BLE001 - give a friendly hint, not a traceback
        _friendly_gui_error(exc)
        return 1
    return 0


def _check() -> int:
    import os

    print(f"{__app_name__} {__version__}")
    print(f"session type : {os.environ.get('XDG_SESSION_TYPE', 'unknown')}")
    print(f"DISPLAY      : {os.environ.get('DISPLAY') or '(unset)'}")
    print(f"WAYLAND      : {os.environ.get('WAYLAND_DISPLAY') or '(unset)'}")

    try:
        import tkinter  # noqa: F401
        print("tkinter      : available")
    except Exception as exc:  # noqa: BLE001
        print(f"tkinter      : MISSING ({exc}) — install 'python3-tk'")

    try:
        import mss  # noqa: F401
        print("mss (capture): available")
    except Exception as exc:  # noqa: BLE001
        print(f"mss (capture): MISSING ({exc})")

    from .clicker import Clicker

    print(f"click backend: {Clicker().backend_name}")
    return 0


def _friendly_gui_error(exc: Exception) -> None:
    msg = str(exc).lower()
    print(f"Failed to start the GUI: {exc}", file=sys.stderr)
    if "display" in msg or "tclerror" in type(exc).__name__.lower():
        print(
            "\nNo graphical display was found. ScreenWatch needs a desktop "
            "session.\nIf you are on a server, run it on the machine with the "
            "screen you want to watch.",
            file=sys.stderr,
        )
    if "tkinter" in msg or "no module named" in msg:
        print("\nTkinter may be missing. On Debian/Ubuntu: sudo apt install python3-tk",
              file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())

"""Command-line logic for ScreenWatch.

Lives here rather than in ``__main__.py`` because PyInstaller (used for the
standalone Windows .exe) has special, hardcoded handling for any module
literally named ``__main__`` and fails to bundle one referenced by name
from elsewhere -- confirmed for real: ``ModuleNotFoundError: No module
named 'screenwatch.__main__'`` even with a matching ``--hidden-import``.
``__main__.py`` is now a thin shim that just imports :func:`main` from here.
"""

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
    import platform

    print(f"{__app_name__} {__version__}")
    print(f"platform     : {platform.system()} {platform.release()}")
    if sys.platform.startswith("linux"):
        print(f"session type : {os.environ.get('XDG_SESSION_TYPE', 'unknown')}")
        print(f"DISPLAY      : {os.environ.get('DISPLAY') or '(unset)'}")
        print(f"WAYLAND      : {os.environ.get('WAYLAND_DISPLAY') or '(unset)'}")

    try:
        import tkinter  # noqa: F401
        print("tkinter      : available")
    except Exception as exc:  # noqa: BLE001
        hint = " — install 'python3-tk'" if sys.platform.startswith("linux") else ""
        print(f"tkinter      : MISSING ({exc}){hint}")

    try:
        import mss  # noqa: F401
        print("mss (capture): available")
    except Exception as exc:  # noqa: BLE001
        print(f"mss (capture): MISSING ({exc})")

    try:
        import customtkinter as ctk

        # Reads the theme's JSON off disk relative to the installed package
        # -- doesn't need a display, but does prove PyInstaller actually
        # bundled CustomTkinter's assets/themes/*.json (a real past failure
        # mode: the import succeeds but this raises FileNotFoundError).
        ctk.set_default_color_theme("green")
        print("customtkinter: available (theme assets found)")
    except Exception as exc:  # noqa: BLE001
        print(f"customtkinter: MISSING ({exc})")

    from .clicker import Clicker
    from .sound import Beeper

    print(f"click backend: {Clicker().backend_name}")
    beeper = Beeper()
    beeper._resolve()  # noqa: SLF001 - diagnostics only, resolves without playing
    print(f"sound backend: {beeper.backend}")
    from .config import default_config_path

    print(f"config path  : {default_config_path()}")
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

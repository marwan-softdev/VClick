"""PyInstaller entry point.

Pointing PyInstaller directly at screenwatch/__main__.py runs it as a
standalone top-level script with no package context, which breaks its
internal relative import (``from . import __app_name__, __version__``) --
confirmed for real: "ImportError: attempted relative import with no known
parent package". Importing screenwatch as a regular package here instead
(same as ``python -m screenwatch`` or the gui-scripts entry point does)
keeps that context intact.
"""
import sys

from screenwatch.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

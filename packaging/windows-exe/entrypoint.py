"""PyInstaller entry point.

Pointing PyInstaller directly at vclick/__main__.py runs it as a
standalone top-level script with no package context, which breaks its
internal relative imports -- confirmed for real: "ImportError: attempted
relative import with no known parent package". Importing vclick's CLI
logic from vclick.cli (not vclick.__main__) instead avoids that
*and* a separate PyInstaller quirk where it fails to bundle a package
submodule literally named __main__, also confirmed for real.
"""
import sys

from vclick.cli import main

if __name__ == "__main__":
    sys.exit(main())

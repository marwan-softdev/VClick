#!/usr/bin/env bash
# Convenience launcher for ScreenWatch.
# Uses ./.venv if it exists (created by install.sh), otherwise the system python.
set -euo pipefail
cd "$(dirname "$0")"

if [ -x ".venv/bin/screenwatch" ]; then
    exec .venv/bin/screenwatch "$@"
elif [ -x ".venv/bin/python" ]; then
    exec .venv/bin/python -m screenwatch "$@"
fi

exec python3 -m screenwatch "$@"

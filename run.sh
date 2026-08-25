#!/usr/bin/env bash
# Convenience launcher for VClick.
# Uses ./.venv if it exists (created by install.sh), otherwise the system python.
set -euo pipefail
cd "$(dirname "$0")"

if [ -x ".venv/bin/vclick" ]; then
    exec .venv/bin/vclick "$@"
elif [ -x ".venv/bin/python" ]; then
    exec .venv/bin/python -m vclick "$@"
fi

exec python3 -m vclick "$@"

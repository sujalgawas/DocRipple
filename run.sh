#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 &>/dev/null; then
    exec python3 run.py "$@"
elif command -v python &>/dev/null; then
    exec python run.py "$@"
else
    echo "[DocRipple ERROR] Python is required to run the services." >&2
    exit 1
fi

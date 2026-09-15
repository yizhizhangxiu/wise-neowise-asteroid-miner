#!/usr/bin/env bash
set -euo pipefail
CFG="${1:-target.example.toml}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
exec "$PYTHON_BIN" -m wise_miner "$CFG"

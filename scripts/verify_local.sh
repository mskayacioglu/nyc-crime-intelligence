#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

if [[ $# -gt 1 || ( $# -eq 1 && "${1:-}" != "--full-data" ) ]]; then
  echo "Usage: $0 [--full-data]" >&2
  exit 2
fi

"$PYTHON_BIN" -c 'import sys; ok=(3, 10) <= sys.version_info[:2] <= (3, 14); raise SystemExit(0 if ok else "Python 3.10 through 3.14 is required.")'
"$PYTHON_BIN" -c 'from importlib.metadata import version; actual=version("duckdb"); raise SystemExit(0 if actual == "1.5.4" else f"DuckDB 1.5.4 is required, found {actual}.")'
node -e 'const [major, minor] = process.versions.node.split(".").map(Number); const ok = (major === 20 && minor >= 19) || (major === 22 && minor >= 13) || major >= 24; if (!ok) { throw new Error("Node ^20.19.0, ^22.13.0, or >=24.0.0 is required") }'
NPM_VERSION="$(npm --version)"
if (( ${NPM_VERSION%%.*} < 10 )); then
  echo "npm 10 or newer is required; found $NPM_VERSION." >&2
  exit 1
fi

check_port() {
  "$PYTHON_BIN" -c 'import socket; sock=socket.socket(); sock.bind(("127.0.0.1", 4173)); sock.close()' || {
    echo "Port 4173 is in use; stop the listener and rerun verification." >&2
    exit 1
  }
}

check_port

cd "$PROJECT_ROOT"
"$PYTHON_BIN" -m unittest discover -s tests -p 'test_*_contract.py'

if [[ $# -eq 1 ]]; then
  "$PYTHON_BIN" -m unittest discover -s tests/integration -p 'test_*_integration.py'
fi

cd "$PROJECT_ROOT/dashboard"
npm ci
npm run lint
npm test
npm run build
npm audit --omit=dev

cd "$PROJECT_ROOT"
git diff --check HEAD
check_port

echo "Local verification passed."

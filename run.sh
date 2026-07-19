#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_DIR="$SCRIPT_DIR/dashboard"
DASHBOARD_HOST="${DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_PORT="${DASHBOARD_PORT:-4173}"

usage() {
  cat <<'EOF'
Usage: ./run.sh

Starts the NYC Crime Intelligence dashboard from the repository root.
Missing or stale frontend dependencies are installed from the lockfile.

Optional environment variables:
  DASHBOARD_HOST  Bind host (default: 127.0.0.1)
  DASHBOARD_PORT  Bind port (default: 4173)

Example:
  DASHBOARD_PORT=3000 ./run.sh
EOF
}

if [[ $# -gt 0 ]]; then
  if [[ $# -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
    usage
    exit 0
  fi
  usage >&2
  exit 2
fi

if [[ -z "$DASHBOARD_HOST" ]]; then
  echo "DASHBOARD_HOST must not be empty." >&2
  exit 2
fi

if [[ ! "$DASHBOARD_PORT" =~ ^[0-9]+$ || ${#DASHBOARD_PORT} -gt 5 ]]; then
  echo "DASHBOARD_PORT must be an integer from 1 through 65535." >&2
  exit 2
fi

DASHBOARD_PORT_NUMBER=$((10#$DASHBOARD_PORT))
if (( DASHBOARD_PORT_NUMBER < 1 || DASHBOARD_PORT_NUMBER > 65535 )); then
  echo "DASHBOARD_PORT must be an integer from 1 through 65535." >&2
  exit 2
fi
DASHBOARD_PORT="$DASHBOARD_PORT_NUMBER"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is required. Install Node 24.5.0 or run 'nvm use'." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm 10 or newer is required." >&2
  exit 1
fi

node -e '
const [major, minor] = process.versions.node.split(".").map(Number)
const supported =
  (major === 20 && minor >= 19) ||
  (major === 22 && minor >= 13) ||
  major >= 24
if (!supported) {
  console.error(`Unsupported Node.js ${process.versions.node}. Use ^20.19.0, ^22.13.0, or >=24.0.0.`)
  process.exit(1)
}
'

NPM_VERSION="$(npm --version)"
if (( ${NPM_VERSION%%.*} < 10 )); then
  echo "npm 10 or newer is required; found $NPM_VERSION." >&2
  exit 1
fi

cd "$DASHBOARD_DIR"

if [[ ! -d node_modules || ! -f node_modules/.package-lock.json ||
  package-lock.json -nt node_modules/.package-lock.json ]]; then
  echo "Installing dashboard dependencies from package-lock.json..."
  npm ci
fi

echo "Starting NYC Crime Intelligence at http://$DASHBOARD_HOST:$DASHBOARD_PORT/"
echo "Press Ctrl+C to stop."

VITE_ARGS=(--port "$DASHBOARD_PORT" --strictPort)
if [[ "$DASHBOARD_HOST" != "127.0.0.1" ]]; then
  VITE_ARGS=(--host "$DASHBOARD_HOST" "${VITE_ARGS[@]}")
fi

exec npm run dev -- "${VITE_ARGS[@]}"

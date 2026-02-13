#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Virtualenv not found. Run: scripts/setup_env.sh"
  exit 1
fi

# Use venv's python to run the agent (no need to activate in current shell)
"$VENV_DIR/bin/python" "$PROJECT_ROOT/langchain-agent.py" "$@"

#!/usr/bin/env bash
set -euo pipefail

# Create virtualenv in ./venv (if not present) and install pinned requirements
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/venv"
REQUIREMENTS="$PROJECT_ROOT/requirements.txt"

echo "Project root: $PROJECT_ROOT"

if [ ! -f "$REQUIREMENTS" ]; then
  echo "requirements.txt not found at $REQUIREMENTS"
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtualenv at $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
fi

# Activate venv for this script
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing pinned requirements..."
pip install -r "$REQUIREMENTS"

echo "Done. To use the environment, run: source venv/bin/activate"

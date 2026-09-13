#!/usr/bin/env bash
# Garuda AgroGod - Unified Launch Script
# Ponytail: 10-line runner to launch server and cockpit

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$DIR/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[Setup] Virtual environment not found. Creating..."
    python3 -m venv "$DIR/.venv"
    "$DIR/.venv/bin/pip" install fastapi uvicorn
fi

echo "================================================="
echo "  GARUDA // AGRO-GOD COMMAND DECK STARTING      "
echo "  Local Cockpit: http://localhost:8000           "
echo "  WebSocket:    ws://localhost:8000/ws/cockpit   "
echo "================================================="

# Start backend server
$VENV_PYTHON "$DIR/server/main.py"

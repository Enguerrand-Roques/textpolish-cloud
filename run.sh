#!/bin/bash
# Creates the venv on first run, then launches the app.

set -e

VENV="venv"

if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV"
    echo "Installing dependencies..."
    "$VENV/bin/pip" install -r requirements.txt
fi

exec "$VENV/bin/python" main.py

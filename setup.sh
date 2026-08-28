#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "[1/4] Creating Python virtual environment..."
    python3 -m venv .venv
fi

echo "[2/4] Installing Python dependencies..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "[3/4] Installing Playwright Chromium..."
.venv/bin/python -m playwright install chromium

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[4/4] Created .env from .env.example."
else
    echo "[4/4] Existing .env preserved."
fi

echo "Setup complete. Edit .env, then run ./run.sh"

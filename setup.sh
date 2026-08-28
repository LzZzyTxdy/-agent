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

if command -v google-chrome >/dev/null 2>&1 \
    || command -v google-chrome-stable >/dev/null 2>&1 \
    || command -v chromium >/dev/null 2>&1 \
    || command -v chromium-browser >/dev/null 2>&1 \
    || [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
    echo "[3/4] System Chrome/Chromium found; bundled Chromium is not required."
else
    echo "[3/4] Chrome not found; installing Playwright Chromium..."
    if ! .venv/bin/python -m playwright install chromium; then
        echo "Chromium installation failed. Install Google Chrome manually or retry setup.sh." >&2
        exit 1
    fi
fi

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[4/4] Created .env from .env.example."
else
    echo "[4/4] Existing .env preserved."
fi

echo "Setup complete. Edit .env, then run ./run.sh"

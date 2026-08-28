#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "Virtual environment not found. Run ./setup.sh first." >&2
    exit 1
fi
if [ ! -f ".env" ]; then
    echo ".env not found. Run ./setup.sh, then enter your API and target URL." >&2
    exit 1
fi
if grep -Eq 'TARGET_URL=https://example\.com/quiz|LLM_API_KEY=your-api-key|LLM_MODEL=your-model-name' .env; then
    echo "Edit .env and replace the example target URL, API key, and model name first." >&2
    exit 1
fi

exec .venv/bin/python main.py "$@"

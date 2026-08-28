"""Append-only JSONL recorder for crash-resilient run history."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class RunRecorder:
    def __init__(self, runs_dir: Path) -> None:
        runs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.path = runs_dir / f"{stamp}.jsonl"

    def append(self, event: Dict[str, Any]) -> None:
        record = {**event, "timestamp": datetime.now(timezone.utc).isoformat()}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()

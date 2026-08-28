"""Bounded public-web search with a persistent query cache."""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List

from ddgs import DDGS

from retrieval.models import Evidence

LOGGER = logging.getLogger(__name__)


class WebSearchRetriever:
    def __init__(self, cache_path: Path, timeout_seconds: int, backend: str) -> None:
        self.cache_path = cache_path
        self.timeout_seconds = timeout_seconds
        self.backend = backend
        self._disabled_after_failure = False
        self._cache: Dict[str, List[Dict[str, str]]] = {}
        if cache_path.exists():
            try:
                raw = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._cache = raw
            except (OSError, json.JSONDecodeError):
                pass

    def search(self, query: str, limit: int) -> List[Evidence]:
        cache_key = " ".join(query.split())[:500]
        raw_results = self._cache.get(cache_key)
        if raw_results is None:
            if self._disabled_after_failure:
                return []
            try:
                raw_results = DDGS(timeout=self.timeout_seconds).text(
                    cache_key,
                    region="cn-zh",
                    safesearch="moderate",
                    max_results=limit,
                    backend=self.backend,
                )
            except Exception as exc:
                LOGGER.warning("Web search unavailable: %s", exc)
                self._disabled_after_failure = True
                return []
            self._cache[cache_key] = [
                {
                    "title": str(result.get("title", "")),
                    "href": str(result.get("href", "")),
                    "body": str(result.get("body", "")),
                }
                for result in raw_results
            ]
            self._save()
            raw_results = self._cache[cache_key]
        return [
            Evidence(
                source=result.get("href", ""),
                title=result.get("title", "Web result"),
                content=result.get("body", ""),
                score=float(limit - index),
                kind="web_search",
            )
            for index, result in enumerate(raw_results[:limit])
            if result.get("body")
        ]

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, self.cache_path)

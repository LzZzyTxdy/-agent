"""Cached PDF extraction and lightweight Chinese BM25 retrieval."""

import json
import logging
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Counter as CounterType, Dict, Iterable, List, Tuple

from pypdf import PdfReader

from retrieval.models import Evidence

LOGGER = logging.getLogger(__name__)
INDEX_VERSION = 1
CHINESE_SEQUENCE = re.compile(r"[\u3400-\u9fff]+")
WORD = re.compile(r"[A-Za-z0-9_]{2,}")


def tokenize(text: str) -> List[str]:
    """Tokenize Chinese into overlapping n-grams and retain Latin words."""
    tokens: List[str] = []
    for sequence in CHINESE_SEQUENCE.findall(text):
        for size in (2, 3, 4):
            tokens.extend(
                sequence[index : index + size]
                for index in range(max(0, len(sequence) - size + 1))
            )
    tokens.extend(word.casefold() for word in WORD.findall(text))
    return tokens


class LocalPdfRetriever:
    """Search text PDFs found in the project using an on-disk cached index."""

    def __init__(
        self,
        project_dir: Path,
        pdf_glob: str,
        index_path: Path,
        chunk_chars: int,
    ) -> None:
        self.project_dir = project_dir
        self.pdf_glob = pdf_glob
        self.index_path = index_path
        self.chunk_chars = chunk_chars
        self._chunks: List[Dict[str, object]] = []
        self._counters: List[CounterType[str]] = []
        self._document_frequency: CounterType[str] = Counter()
        self._average_length = 1.0
        self._loaded = False

    def _pdf_paths(self) -> List[Path]:
        return sorted(
            path
            for path in self.project_dir.glob(self.pdf_glob)
            if path.is_file() and path.suffix.casefold() == ".pdf"
        )

    @staticmethod
    def _manifest(paths: Iterable[Path]) -> List[Dict[str, object]]:
        return [
            {
                "path": path.name,
                "size": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
            }
            for path in paths
        ]

    def _load_or_build(self) -> None:
        if self._loaded:
            return
        paths = self._pdf_paths()
        manifest = self._manifest(paths)
        cached = None
        if self.index_path.exists():
            try:
                cached = json.loads(self.index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cached = None
        if (
            isinstance(cached, dict)
            and cached.get("version") == INDEX_VERSION
            and cached.get("manifest") == manifest
            and isinstance(cached.get("chunks"), list)
        ):
            self._chunks = cached["chunks"]
        else:
            self._chunks = self._build(paths)
            self._save(manifest)
        self._prepare_scores()
        self._loaded = True
        LOGGER.info(
            "Local PDF index ready: %d file(s), %d chunk(s)",
            len(paths),
            len(self._chunks),
        )

    def _build(self, paths: Iterable[Path]) -> List[Dict[str, object]]:
        chunks: List[Dict[str, object]] = []
        for path in paths:
            reader = PdfReader(path)
            for page_number, page in enumerate(reader.pages, start=1):
                text = " ".join((page.extract_text() or "").split())
                if not text:
                    continue
                for part_number, content in enumerate(self._split(text), start=1):
                    chunks.append(
                        {
                            "file": path.name,
                            "page": page_number,
                            "part": part_number,
                            "text": content,
                        }
                    )
        return chunks

    def _split(self, text: str) -> List[str]:
        if len(text) <= self.chunk_chars:
            return [text]
        overlap = min(150, self.chunk_chars // 5)
        step = max(1, self.chunk_chars - overlap)
        return [text[start : start + self.chunk_chars] for start in range(0, len(text), step)]

    def _save(self, manifest: List[Dict[str, object]]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.index_path.with_suffix(self.index_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {"version": INDEX_VERSION, "manifest": manifest, "chunks": self._chunks},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.index_path)

    def _prepare_scores(self) -> None:
        self._counters = [Counter(tokenize(str(chunk["text"]))) for chunk in self._chunks]
        self._document_frequency = Counter()
        for counter in self._counters:
            self._document_frequency.update(counter.keys())
        lengths = [sum(counter.values()) for counter in self._counters]
        self._average_length = sum(lengths) / len(lengths) if lengths else 1.0

    def _score(self, query: CounterType[str], document: CounterType[str]) -> float:
        total_documents = max(1, len(self._counters))
        document_length = max(1, sum(document.values()))
        score = 0.0
        for token, query_frequency in query.items():
            frequency = document.get(token, 0)
            if not frequency:
                continue
            document_frequency = self._document_frequency.get(token, 0)
            inverse_frequency = math.log(
                1 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            denominator = frequency + 1.5 * (
                0.25 + 0.75 * document_length / self._average_length
            )
            score += query_frequency * inverse_frequency * frequency * 2.5 / denominator
        return score

    def search(self, query: str, limit: int) -> List[Evidence]:
        self._load_or_build()
        query_counter = Counter(tokenize(query))
        if not query_counter:
            return []
        ranked: List[Tuple[float, int]] = [
            (self._score(query_counter, counter), index)
            for index, counter in enumerate(self._counters)
        ]
        ranked.sort(reverse=True)
        results: List[Evidence] = []
        for score, index in ranked[:limit]:
            if score <= 0:
                continue
            chunk = self._chunks[index]
            results.append(
                Evidence(
                    source=f"{chunk['file']}#page={chunk['page']}",
                    title=f"{chunk['file']} 第 {chunk['page']} 页",
                    content=str(chunk["text"]),
                    score=score,
                    kind="local_pdf",
                )
            )
        return results

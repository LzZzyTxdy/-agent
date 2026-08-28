"""Atomic, order-independent JSON-backed answer cache."""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from models import AnswerDecision, Question

LOGGER = logging.getLogger(__name__)
CACHE_VERSION = 2


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _option_set_hash(options: List[str]) -> str:
    """Hash the option multiset without depending on its display order."""
    payload = json.dumps(
        sorted(_normalize(option) for option in options),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CacheEntry(BaseModel):
    """A cached answer expressed as text instead of unstable page indices."""

    question_text: str = Field(min_length=1)
    question_type: str = Field(min_length=1)
    option_set_hash: str = Field(min_length=1)
    selected_answers: List[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    sources: List[str] = Field(default_factory=list)


class QuestionCache:
    """Stores answers and remaps them to each attempt's option ordering."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: Dict[str, CacheEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("Ignoring unreadable question cache: %s", self.path)
            return

        if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
            # Version 1 stored only raw indices. It cannot be safely migrated
            # because the site randomizes option order between attempts.
            LOGGER.warning(
                "Ignoring legacy question cache with unsafe option indices: %s",
                self.path,
            )
            return

        entries = raw.get("entries")
        if not isinstance(entries, dict):
            LOGGER.warning("Ignoring malformed question cache: %s", self.path)
            return

        for question_id, value in entries.items():
            try:
                self._entries[str(question_id)] = CacheEntry.model_validate(value)
            except ValueError:
                LOGGER.warning(
                    "Skipping malformed cache entry for question %s", question_id
                )

    def get(self, question: Question) -> Optional[AnswerDecision]:
        entry = self._entries.get(question.question_id)
        if entry is None:
            return None

        if (
            entry.question_text != _normalize(question.text)
            or entry.question_type != question.question_type
            or entry.option_set_hash != _option_set_hash(question.options)
        ):
            LOGGER.info(
                "Cache miss for question %s: question or options changed",
                question.question_id,
            )
            return None

        normalized_options = [_normalize(option) for option in question.options]
        # Equal-looking duplicate options cannot be mapped to stable DOM inputs.
        if len(normalized_options) != len(set(normalized_options)):
            LOGGER.info(
                "Cache miss for question %s: duplicate option text", question.question_id
            )
            return None

        indices_by_answer = {
            answer: index for index, answer in enumerate(normalized_options)
        }
        try:
            mapped = sorted(
                indices_by_answer[_normalize(answer)]
                for answer in entry.selected_answers
            )
        except KeyError:
            return None

        if len(mapped) != len(set(mapped)):
            return None
        if question.question_type == "single_choice":
            if len(mapped) != 1:
                return None
            choice = mapped[0]
        else:
            choice = mapped

        return AnswerDecision(
            choice=choice,
            confidence=entry.confidence,
            reason=entry.reason,
            sources=entry.sources,
        )

    def put(self, question: Question, decision: AnswerDecision) -> None:
        normalized_options = [_normalize(option) for option in question.options]
        if len(normalized_options) != len(set(normalized_options)):
            LOGGER.info(
                "Not caching question %s: duplicate option text", question.question_id
            )
            return
        indices = decision.choice_indices
        if any(index < 0 or index >= len(normalized_options) for index in indices):
            raise ValueError("decision contains an out-of-range option index")
        selected_answers = [normalized_options[index] for index in indices]

        self._entries[question.question_id] = CacheEntry(
            question_text=_normalize(question.text),
            question_type=question.question_type,
            option_set_hash=_option_set_hash(question.options),
            selected_answers=selected_answers,
            confidence=decision.confidence,
            reason=decision.reason,
            sources=decision.sources,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "version": CACHE_VERSION,
                    "entries": {
                        key: value.model_dump()
                        for key, value in self._entries.items()
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

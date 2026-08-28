"""Deterministic extraction of the current question from Playwright DOM."""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from playwright.sync_api import Locator, Page

from browser.selectors import (
    ANSWER_LABEL_SELECTORS,
    ANSWER_TYPE_INPUT_SELECTOR,
    NEXT_BUTTON_TEXTS,
    QUESTION_CONTAINER_SELECTORS,
    QUESTION_TEXT_SELECTORS,
)
from exceptions import ExtractionError
from models import Question

ID_PATTERN = re.compile(r"question[_-](\d+)(?:[_-]|$)", re.IGNORECASE)
URL_QUESTION_PATTERN = re.compile(r"/questions/(\d+)(?:/|$)", re.IGNORECASE)


def parse_question_id_from_url(url: str) -> Optional[str]:
    """Extract a numeric question ID from a /questions/<id> URL path."""
    match = URL_QUESTION_PATTERN.search(urlparse(url).path)
    return match.group(1) if match else None


@dataclass(frozen=True)
class ExtractionDiagnostics:
    url: str
    question_matches: int
    question_text: str
    answer_matches: int
    answers: List[str]
    question_id: str
    question_type: str
    next_button_found: bool


class QuestionExtractor:
    """Extracts only loaded, structurally valid questions; visibility is irrelevant."""

    def __init__(self, page: Page) -> None:
        self.page = page

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(value.split())

    def _first_populated_question(self) -> Tuple[Locator, str, int]:
        total = 0
        for selector in QUESTION_TEXT_SELECTORS:
            locator = self.page.locator(selector)
            count = locator.count()
            total += count
            for index in range(count):
                node = locator.nth(index)
                value = node.evaluate(
                    """(el) => {
                        const raw = ('value' in el ? el.value : el.textContent) || '';
                        if (!('value' in el)) return raw;
                        const template = document.createElement('template');
                        template.innerHTML = raw;
                        return template.content.textContent || raw;
                    }"""
                )
                text = self._clean(str(value))
                if text:
                    return node, text, total
        raise ExtractionError(
            f"No populated question text found with selectors: {QUESTION_TEXT_SELECTORS}"
        )

    def _answers(self) -> Tuple[List[str], int]:
        for selector in ANSWER_LABEL_SELECTORS:
            locator = self.page.locator(selector)
            count = locator.count()
            if count:
                values = [
                    self._clean(
                        str(locator.nth(i).evaluate("el => el.textContent || ''"))
                    )
                    for i in range(count)
                ]
                values = [value for value in values if value]
                if values:
                    return values, count
        raise ExtractionError(
            f"No answer text found with selectors: {ANSWER_LABEL_SELECTORS}"
        )

    def _question_id(self, question_node: Locator, text: str, options: List[str]) -> str:
        # Priority 1: explicit, stable DOM data attributes.
        for selector in QUESTION_CONTAINER_SELECTORS:
            nodes = self.page.locator(selector)
            for index in range(min(nodes.count(), 20)):
                node = nodes.nth(index)
                stable_id = node.get_attribute("data-question-id")
                if stable_id:
                    match = re.search(r"\d+", stable_id)
                    if match:
                        return match.group(0)

        # Priority 2: URL after login/navigation, not the configured target URL.
        url_id = parse_question_id_from_url(self.page.url)
        if url_id:
            return url_id

        # Priority 3: element IDs such as question_188767_question_text.
        candidates: List[str] = []
        node_id = question_node.get_attribute("id")
        if node_id:
            candidates.append(node_id)
        for selector in QUESTION_CONTAINER_SELECTORS:
            nodes = self.page.locator(selector)
            for index in range(min(nodes.count(), 20)):
                node_id = nodes.nth(index).get_attribute("id")
                if node_id:
                    candidates.append(node_id)
        for candidate in candidates:
            if candidate.isdigit():
                return candidate
            match = ID_PATTERN.search(candidate)
            if match:
                return match.group(1)
        return Question.fallback_id(text, options)

    def extract(self) -> Question:
        question_node, text, _ = self._first_populated_question()
        options, _ = self._answers()
        if len(options) < 2:
            raise ExtractionError("A choice question must contain at least two options")
        input_types = self.page.locator(ANSWER_TYPE_INPUT_SELECTOR).evaluate_all(
            "els => els.map(el => el.type)"
        )
        question_type = "multiple_choice" if "checkbox" in input_types else "single_choice"
        return Question(
            question_id=self._question_id(question_node, text, options),
            text=text,
            options=options,
            question_type=question_type,
        )

    def diagnostics(self) -> ExtractionDiagnostics:
        node, text, question_count = self._first_populated_question()
        answers, answer_count = self._answers()
        input_types = self.page.locator(ANSWER_TYPE_INPUT_SELECTOR).evaluate_all(
            "els => els.map(el => el.type)"
        )
        return ExtractionDiagnostics(
            url=self.page.url,
            question_matches=question_count,
            question_text=text,
            answer_matches=answer_count,
            answers=answers,
            question_id=self._question_id(node, text, answers),
            question_type=(
                "multiple_choice" if "checkbox" in input_types else "single_choice"
            ),
            next_button_found=any(
                self.page.get_by_text(label, exact=False).count() > 0
                for label in NEXT_BUTTON_TEXTS
            ),
        )

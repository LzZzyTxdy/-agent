"""Solver contract."""

from typing import Protocol

from models import AnswerDecision, Question


class Solver(Protocol):
    def solve(self, question: Question) -> AnswerDecision:
        """Return a validated, zero-based answer decision."""
        ...

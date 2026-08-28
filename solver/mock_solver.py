"""Offline solver useful for exercising browser behavior without an API."""

import random

from models import AnswerDecision, Question


class MockSolver:
    def __init__(self, mode: str = "manual") -> None:
        self.mode = mode

    def solve(self, question: Question) -> AnswerDecision:
        if self.mode == "random":
            choice = random.randrange(len(question.options))
            return AnswerDecision(
                choice=choice, confidence=1.0, reason="Mock random selection"
            )
        while True:
            raw = input(f"Mock solver: enter answer index 0-{len(question.options) - 1}: ")
            try:
                choice = int(raw)
                if 0 <= choice < len(question.options):
                    return AnswerDecision(
                        choice=choice, confidence=1.0, reason="User entered mock answer"
                    )
            except ValueError:
                pass
            print("Invalid index; please try again.")

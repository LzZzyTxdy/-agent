"""Policy barrier between probabilistic solver output and browser actions."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from exceptions import DecisionRejected
from models import AnswerDecision, Question

LOGGER = logging.getLogger(__name__)


class ManualAction(str, Enum):
    ANSWER = "answer"
    SKIP = "skip"
    QUIT = "quit"


@dataclass(frozen=True)
class ManualReview:
    action: ManualAction
    decision: Optional[AnswerDecision] = None


class DecisionPolicy:
    def __init__(self, min_confidence: float, low_confidence_mode: str) -> None:
        self.min_confidence = min_confidence
        self.low_confidence_mode = low_confidence_mode

    @staticmethod
    def validate(question: Question, decision: AnswerDecision) -> None:
        indices = decision.choice_indices
        if question.question_type == "single_choice" and len(indices) != 1:
            raise DecisionRejected(
                "single-choice question requires exactly one answer index"
            )
        if any(not 0 <= index < len(question.options) for index in indices):
            raise DecisionRejected(
                f"choice {decision.choice} contains an index outside "
                f"0..{len(question.options) - 1}"
            )
        if not 0 <= decision.confidence <= 1:
            raise DecisionRejected("confidence must be in [0, 1]")

    @staticmethod
    def manual_review(question: Question, decision: AnswerDecision) -> ManualReview:
        """Ask for an explicit action before any browser click."""
        LOGGER.info("Recommended choice: %s", decision.choice)
        LOGGER.info(
            "Recommended answer: %s",
            " | ".join(question.options[index] for index in decision.choice_indices),
        )
        LOGGER.info("Confidence: %.2f", decision.confidence)
        LOGGER.info("Reason: %s", decision.reason)
        prompt = (
            f"[y] 使用 AI 答案 | [0-{len(question.options) - 1}] 手动指定"
            f"{'（多选用逗号分隔）' if question.question_type == 'multiple_choice' else ''} | "
            "[s] 跳过 | [q] 停止: "
        )
        while True:
            raw = input(prompt).strip().casefold()
            if raw in {"y", "yes"}:
                return ManualReview(ManualAction.ANSWER, decision)
            if raw in {"s", "skip"}:
                return ManualReview(ManualAction.SKIP)
            if raw in {"q", "quit"}:
                return ManualReview(ManualAction.QUIT)
            try:
                choices = [int(part.strip()) for part in raw.split(",")]
                if (
                    choices
                    and all(0 <= choice < len(question.options) for choice in choices)
                    and len(choices) == len(set(choices))
                    and (
                        question.question_type == "multiple_choice"
                        or len(choices) == 1
                    )
                ):
                    return ManualReview(
                        ManualAction.ANSWER,
                        AnswerDecision(
                            choice=(
                                choices
                                if question.question_type == "multiple_choice"
                                else choices[0]
                            ),
                            confidence=1.0,
                            reason="Human selected answer",
                        ),
                    )
            except ValueError:
                pass
            LOGGER.warning("无效输入：%s", raw)

    @staticmethod
    def manual_choice(question: Question, decision: AnswerDecision) -> AnswerDecision:
        review = DecisionPolicy.manual_review(question, decision)
        if review.action is not ManualAction.ANSWER or review.decision is None:
            raise DecisionRejected(f"Manual review ended with action: {review.action.value}")
        return review.decision

    def apply(
        self,
        question: Question,
        decision: AnswerDecision,
        retry_solver: Callable[[], AnswerDecision],
        defer_manual: bool = False,
    ) -> AnswerDecision:
        self.validate(question, decision)
        if decision.confidence >= self.min_confidence:
            return decision
        if self.low_confidence_mode == "accept":
            return decision
        if self.low_confidence_mode == "stop":
            raise DecisionRejected(
                f"confidence {decision.confidence:.2f} below {self.min_confidence:.2f}"
            )
        if self.low_confidence_mode == "retry":
            retried = retry_solver()
            self.validate(question, retried)
            if retried.confidence >= self.min_confidence:
                return retried
            raise DecisionRejected(
                "Retried decision still below minimum confidence"
            )
        return decision if defer_manual else self.manual_choice(question, decision)

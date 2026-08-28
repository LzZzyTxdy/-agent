import pytest
from pydantic import ValidationError

from models import AnswerDecision, Question


def test_question_cleans_text_and_has_stable_fallback_id() -> None:
    question = Question(question_id=" 42 ", text="  hello   world ", options=[" a ", "b"])
    assert question.question_id == "42"
    assert question.text == "hello world"
    assert question.options == ["a", "b"]
    assert Question.fallback_id("q", ["a", "b"]) == Question.fallback_id("q", ["a", "b"])


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_answer_decision_rejects_bad_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError):
        AnswerDecision(choice=0, confidence=confidence, reason="x")


def test_answer_decision_accepts_multiple_unique_indices() -> None:
    decision = AnswerDecision(choice=[1, 3, 4], confidence=0.9, reason="multiple")
    assert decision.choice_indices == [1, 3, 4]


@pytest.mark.parametrize("choice", [[], [1, 1]])
def test_answer_decision_rejects_invalid_multiple_shape(choice: list[int]) -> None:
    with pytest.raises(ValidationError):
        AnswerDecision(choice=choice, confidence=0.9, reason="bad")

import pytest

from exceptions import DecisionRejected
from models import AnswerDecision, Question
from policy import DecisionPolicy, ManualAction


@pytest.fixture
def question() -> Question:
    return Question(question_id="1", text="Q", options=["A", "B"])


def test_policy_accepts_valid_high_confidence(question: Question) -> None:
    policy = DecisionPolicy(0.7, "stop")
    decision = AnswerDecision(choice=1, confidence=0.9, reason="because")
    assert policy.apply(question, decision, lambda: decision) == decision


def test_policy_rejects_choice_out_of_range(question: Question) -> None:
    policy = DecisionPolicy(0.7, "stop")
    with pytest.raises(DecisionRejected):
        policy.validate(question, AnswerDecision(choice=2, confidence=0.9, reason="x"))


def test_low_confidence_retry(question: Question) -> None:
    policy = DecisionPolicy(0.7, "retry")
    low = AnswerDecision(choice=0, confidence=0.4, reason="uncertain")
    high = AnswerDecision(choice=1, confidence=0.8, reason="rechecked")
    assert policy.apply(question, low, lambda: high) == high


def test_manual_review_can_skip(question: Question, monkeypatch: pytest.MonkeyPatch) -> None:
    decision = AnswerDecision(choice=0, confidence=0.8, reason="test")
    monkeypatch.setattr("builtins.input", lambda prompt: "s")
    review = DecisionPolicy.manual_review(question, decision)
    assert review.action is ManualAction.SKIP
    assert review.decision is None


def test_policy_accepts_multiple_choice_indices() -> None:
    question = Question(
        question_id="multi",
        text="Select all",
        options=["A", "B", "C", "D"],
        question_type="multiple_choice",
    )
    decision = AnswerDecision(choice=[1, 3], confidence=0.9, reason="both")
    DecisionPolicy.validate(question, decision)


def test_policy_rejects_multiple_indices_for_single_choice(question: Question) -> None:
    with pytest.raises(DecisionRejected):
        DecisionPolicy.validate(
            question,
            AnswerDecision(choice=[0, 1], confidence=0.9, reason="bad"),
        )


def test_manual_review_parses_comma_separated_indices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = Question(
        question_id="multi",
        text="Select all",
        options=["A", "B", "C", "D"],
        question_type="multiple_choice",
    )
    decision = AnswerDecision(choice=[0], confidence=0.5, reason="test")
    monkeypatch.setattr("builtins.input", lambda prompt: "1,3")
    review = DecisionPolicy.manual_review(question, decision)
    assert review.decision is not None
    assert review.decision.choice == [1, 3]

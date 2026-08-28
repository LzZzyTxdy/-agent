import json
from pathlib import Path

from models import AnswerDecision, Question
from storage import QuestionCache


def make_question(
    options: list[str],
    *,
    text: str = "question",
    question_type: str = "single_choice",
) -> Question:
    return Question(
        question_id="q1",
        text=text,
        options=options,
        question_type=question_type,
    )


def test_cache_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    question = make_question(["A", "B", "C"])
    decision = AnswerDecision(
        choice=1, confidence=0.9, reason="test", sources=["reference.pdf"]
    )
    QuestionCache(path).put(question, decision)
    assert QuestionCache(path).get(question) == decision


def test_cache_remaps_answer_after_options_are_shuffled(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    original = make_question(["A", "B", "C"])
    shuffled = make_question(["C", "A", "B"])
    QuestionCache(path).put(
        original, AnswerDecision(choice=1, confidence=0.9, reason="B is correct")
    )

    remapped = QuestionCache(path).get(shuffled)

    assert remapped is not None
    assert remapped.choice == 2


def test_cache_remaps_multiple_answers_after_shuffle(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    original = make_question(
        ["A", "B", "C", "D"], question_type="multiple_choice"
    )
    shuffled = make_question(
        ["D", "C", "A", "B"], question_type="multiple_choice"
    )
    QuestionCache(path).put(
        original, AnswerDecision(choice=[0, 2], confidence=0.9, reason="A and C")
    )

    remapped = QuestionCache(path).get(shuffled)

    assert remapped is not None
    assert remapped.choice == [1, 2]


def test_changed_question_or_options_invalidates_entry(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    original = make_question(["A", "B", "C"])
    cache = QuestionCache(path)
    cache.put(original, AnswerDecision(choice=1, confidence=0.9, reason="test"))

    assert cache.get(make_question(["A", "B", "D"])) is None
    assert cache.get(make_question(["A", "B", "C"], text="new question")) is None


def test_cache_file_is_versioned_and_stores_answer_text(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    question = make_question(["A", "B", "C"])
    QuestionCache(path).put(
        question, AnswerDecision(choice=1, confidence=0.9, reason="test")
    )

    raw = json.loads(path.read_text(encoding="utf-8"))

    assert raw["version"] == 2
    assert raw["entries"]["q1"]["selected_answers"] == ["B"]
    assert "choice" not in raw["entries"]["q1"]


def test_legacy_index_cache_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    path.write_text(
        json.dumps({"q1": {"choice": 1, "confidence": 0.9, "reason": "old"}}),
        encoding="utf-8",
    )
    assert QuestionCache(path).get(make_question(["A", "B", "C"])) is None


def test_corrupt_cache_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    path.write_text("not-json", encoding="utf-8")
    assert QuestionCache(path).get(make_question(["A", "B", "C"])) is None

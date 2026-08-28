import pytest
from pydantic import ValidationError

from solver.llm_solver import parse_decision_json


def test_parse_plain_json() -> None:
    result = parse_decision_json('{"choice": 2, "confidence": 0.93, "reason": "ok"}')
    assert result.choice == 2


def test_parse_fenced_json() -> None:
    result = parse_decision_json('```json\n{"choice": 0, "confidence": 1, "reason": "ok"}\n```')
    assert result.choice == 0


def test_parse_rejects_bad_confidence() -> None:
    with pytest.raises(ValidationError):
        parse_decision_json('{"choice": 0, "confidence": 2, "reason": "bad"}')


def test_parse_multiple_choice_json() -> None:
    result = parse_decision_json(
        '{"choice": [1, 3, 4], "confidence": 0.9, "reason": "all apply"}'
    )
    assert result.choice_indices == [1, 3, 4]

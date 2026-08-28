import pytest

from extractor import parse_question_id_from_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://elearning.example/courses/1/quizzes/2/take/questions/188767",
            "188767",
        ),
        (
            "https://elearning.example/take/questions/188767?preview=1",
            "188767",
        ),
        ("https://elearning.example/take/questions", None),
    ],
)
def test_parse_question_id_from_url(url: str, expected: str | None) -> None:
    assert parse_question_id_from_url(url) == expected

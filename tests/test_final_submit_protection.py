import pytest
from types import SimpleNamespace

import browser.controller as controller_module
from browser.controller import BrowserController
from browser.selectors import is_final_submit_text
from exceptions import BrowserStateError
from models import Question


class FakeControl:
    def __init__(self, text: str) -> None:
        self.text = text

    def evaluate(self, expression: str) -> str:
        return self.text


@pytest.mark.parametrize(
    "text",
    ["提交试卷", "提交所有答案", "结束并提交", "Submit Quiz", "Finish attempt"],
)
def test_final_submit_text_is_protected(text: str) -> None:
    assert is_final_submit_text(text)


def test_next_text_is_not_final_submit() -> None:
    assert not is_final_submit_text("下一页")


def test_controller_refuses_final_submit_control() -> None:
    controller = object.__new__(BrowserController)
    with pytest.raises(BrowserStateError, match="Refusing"):
        controller._assert_safe_next(FakeControl("Submit Quiz"))  # type: ignore[arg-type]


def test_logged_url_drops_sensitive_query_and_fragment() -> None:
    assert BrowserController._safe_url(
        "https://example.test/take/questions/42?token=secret#answer"
    ) == "https://example.test/take/questions/42"


def test_final_control_does_not_finish_while_next_exists() -> None:
    controller = object.__new__(BrowserController)
    controller._final_submit_control = lambda: object()  # type: ignore[method-assign]
    controller._next_button = lambda: object()  # type: ignore[method-assign]
    assert not controller.is_finished()


def test_final_control_finishes_when_next_is_absent() -> None:
    controller = object.__new__(BrowserController)
    controller._final_submit_control = lambda: object()  # type: ignore[method-assign]
    controller._next_button = lambda: None  # type: ignore[method-assign]
    assert controller.is_finished()


def test_multiple_choice_applies_exact_checkbox_set() -> None:
    controller = object.__new__(BrowserController)
    calls: list[tuple[int, bool]] = []
    controller.settings = SimpleNamespace(browser_max_retries=1, page_timeout_ms=1500)
    controller._require_page = lambda: SimpleNamespace(  # type: ignore[method-assign]
        wait_for_timeout=lambda milliseconds: None
    )
    controller.selected_answer_indices = lambda count: [1, 3]  # type: ignore[method-assign]
    controller._set_answer_state = (  # type: ignore[method-assign]
        lambda index, selected: calls.append((index, selected))
    )
    assert controller.select_answers([1, 3], option_count=4, multiple=True) == [1, 3]
    assert calls == [(0, False), (2, False), (1, True), (3, True)]


def test_last_question_is_read_before_finish_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = Question(question_id="last", text="Last question", options=["A", "B"])

    class FakeExtractor:
        def __init__(self, page: object) -> None:
            pass

        def extract(self) -> Question:
            return question

    controller = object.__new__(BrowserController)
    controller._require_page = lambda: object()  # type: ignore[method-assign]
    controller.is_finished = lambda: True  # type: ignore[method-assign]
    monkeypatch.setattr(controller_module, "QuestionExtractor", FakeExtractor)

    state = controller.read_page_state()
    assert state.question == question
    assert not state.finished

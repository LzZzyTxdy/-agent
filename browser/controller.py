"""Deterministic Playwright operations and browser state synchronization."""

import logging
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from browser.selectors import (
    ANSWER_INPUT_SELECTOR,
    ANSWER_LABEL_DESCENDANT_SELECTOR,
    ANSWER_ROW_SELECTORS,
    FINAL_CONTROL_SELECTORS,
    FINAL_SUBMIT_TEXTS,
    NEXT_BUTTON_TEXTS,
    NEXT_CSS_SELECTORS,
    QUESTION_PAGE_URL_MARKERS,
    QUESTION_TEXT_SELECTORS,
    is_final_submit_text,
)
from config import Settings
from exceptions import BrowserStateError, ExtractionError
from extractor import QuestionExtractor
from models import Question

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageState:
    question: Optional[Question]
    finished: bool


class BrowserController:
    """Owns browser lifecycle and deterministic page actions, never answer semantics."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def start(self) -> None:
        self._playwright = sync_playwright().start()
        kwargs = {"headless": self.settings.headless}
        if self.settings.browser_channel:
            kwargs["channel"] = self.settings.browser_channel
        try:
            self._browser = self._playwright.chromium.launch(**kwargs)
        except PlaywrightError:
            if not self.settings.browser_channel:
                raise
            LOGGER.warning(
                "Chrome channel unavailable; falling back to bundled Chromium."
            )
            kwargs.pop("channel", None)
            self._browser = self._playwright.chromium.launch(**kwargs)
        self._context = self._browser.new_context()
        self.page = self._context.new_page()
        self.page.set_default_timeout(self.settings.page_timeout_ms)
        self.page.goto(
            self.settings.target_url,
            wait_until="domcontentloaded",
            timeout=self.settings.page_timeout_ms,
        )

    def wait_for_user_login(self) -> None:
        input(
            "请在浏览器中手动登录并进入第一题，然后回到终端按 Enter 开始..."
        )
        self._adopt_question_page()

    def wait_for_manual_final_review(self) -> None:
        """Keep the browser alive so the user can review/submit the last answer."""
        page = self._require_page()
        page.bring_to_front()
        input(
            "最后一题已选择并完成 DOM 验证。浏览器将保持打开；"
            "请人工检查答案并自行决定是否提交。完成后回到终端按 Enter 关闭浏览器..."
        )

    @staticmethod
    def _safe_url(url: str) -> str:
        """Remove query/fragment data before logging a browser URL."""
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    @staticmethod
    def _page_has_question(page: Page) -> bool:
        for selector in QUESTION_TEXT_SELECTORS:
            try:
                nodes = page.locator(selector)
                for index in range(nodes.count()):
                    value = nodes.nth(index).evaluate(
                        "el => ('value' in el ? el.value : el.textContent) || ''"
                    )
                    if str(value).strip():
                        return True
            except PlaywrightError:
                continue
        return False

    def _adopt_question_page(self) -> None:
        """Follow SSO popups/new tabs and select the page containing the quiz."""
        if self._context is None:
            raise BrowserStateError("Browser context is not available")
        pages = [page for page in self._context.pages if not page.is_closed()]
        if not pages:
            raise BrowserStateError("No open browser pages remain after login")

        ranked = []
        for index, page in enumerate(pages):
            safe_url = self._safe_url(page.url)
            url_score = 20 if any(
                marker in safe_url for marker in QUESTION_PAGE_URL_MARKERS
            ) else 0
            question_score = 100 if self._page_has_question(page) else 0
            ranked.append((question_score + url_score + index, page))

        _, selected = max(ranked, key=lambda item: item[0])
        self.page = selected
        self.page.set_default_timeout(self.settings.page_timeout_ms)
        self.page.bring_to_front()
        LOGGER.info(
            "Using browser page %d/%d: %s",
            pages.index(selected) + 1,
            len(pages),
            self._safe_url(selected.url),
        )

    def _require_page(self) -> Page:
        if self.page is None or self.page.is_closed():
            raise BrowserStateError("Browser page is not available or was closed")
        return self.page

    def read_page_state(self) -> PageState:
        page = self._require_page()
        try:
            # A final-submit control can coexist with the last unanswered
            # question. Always prefer a valid question over finish detection.
            question = QuestionExtractor(page).extract()
            return PageState(question=question, finished=False)
        except ExtractionError:
            if self.is_finished():
                return PageState(question=None, finished=True)
            raise

    def _answer_row(self, index: int) -> Locator:
        page = self._require_page()
        for selector in ANSWER_ROW_SELECTORS:
            rows = page.locator(selector)
            if rows.count() > index:
                return rows.nth(index)
        raise BrowserStateError(f"Cannot locate answer row at index {index}")

    def select_answer(self, index: int) -> None:
        """Ensure one answer is selected without toggling an already checked box."""
        self._set_answer_state(index, selected=True)

    def select_answers(
        self, indices: list[int], option_count: int, multiple: bool
    ) -> list[int]:
        """Apply an exact answer set and verify every resulting control state."""
        targets = set(indices)
        if not targets or any(index < 0 or index >= option_count for index in targets):
            raise BrowserStateError(f"Invalid answer indices: {indices}")
        if not multiple:
            if len(targets) != 1:
                raise BrowserStateError("Single-choice question requires one answer")
            self.select_answer(next(iter(targets)))
            actual = self.selected_answer_indices(option_count)
            if set(actual) != targets:
                raise BrowserStateError(
                    f"Selected answers {actual} do not match requested {sorted(targets)}"
                )
            return actual

        for verification_attempt in range(self.settings.browser_max_retries):
            # Clear stale selections first, then select desired answers. Each
            # changed checkbox waits for Canvas AJAX traffic to settle.
            for index in range(option_count):
                if index not in targets:
                    self._set_answer_state(index, selected=False)
            for index in sorted(targets):
                self._set_answer_state(index, selected=True)

            actual = self._wait_for_stable_selection(targets, option_count)
            if actual is not None:
                return actual
            LOGGER.warning(
                "Multiple-choice verification %d/%d mismatch: requested=%s actual=%s",
                verification_attempt + 1,
                self.settings.browser_max_retries,
                sorted(targets),
                self.selected_answer_indices(option_count),
            )
        actual = self.selected_answer_indices(option_count)
        raise BrowserStateError(
            f"Selected answers {actual} do not match requested {sorted(targets)}"
        )

    def _wait_for_stable_selection(
        self, targets: set[int], option_count: int
    ) -> Optional[list[int]]:
        """Require the exact checked set to remain stable after async saves."""
        page = self._require_page()
        consecutive_matches = 0
        max_checks = max(15, min(50, self.settings.page_timeout_ms // 100))
        for _ in range(max_checks):
            actual = self.selected_answer_indices(option_count)
            if set(actual) == targets:
                consecutive_matches += 1
                if consecutive_matches >= 10:
                    return actual
            else:
                consecutive_matches = 0
            page.wait_for_timeout(100)
        return None

    def selected_answer_indices(self, option_count: int) -> list[int]:
        """Read the actual checked/selected answer indices from the DOM."""
        selected = []
        for index in range(option_count):
            state = self._selected_state(self._answer_row(index))
            if state is None:
                raise BrowserStateError(
                    f"Cannot determine selected state for answer index {index}"
                )
            if state:
                selected.append(index)
        return selected

    def _click_answer_control(self, control: Locator) -> None:
        """Click once and let the page's asynchronous answer save settle."""
        page = self._require_page()
        control.click()
        try:
            page.wait_for_load_state(
                "networkidle", timeout=min(self.settings.page_timeout_ms, 3000)
            )
        except PlaywrightTimeoutError:
            # Some quiz pages maintain background polling. DOM verification
            # below remains authoritative when network-idle is unavailable.
            LOGGER.debug("Answer save did not reach networkidle before timeout")

    def _set_native_input(self, control: Locator, selected: bool) -> None:
        """Use Playwright's idempotent native checkbox/radio operation."""
        page = self._require_page()
        if selected:
            control.check()
        else:
            control.uncheck()
        try:
            page.wait_for_load_state(
                "networkidle", timeout=min(self.settings.page_timeout_ms, 3000)
            )
        except PlaywrightTimeoutError:
            LOGGER.debug("Native answer save did not reach networkidle before timeout")

    def _set_answer_state(self, index: int, selected: bool) -> None:
        last_error: Optional[BaseException] = None
        for attempt in range(self.settings.browser_max_retries):
            row = self._answer_row(index)
            if self._selected_state(row) is selected:
                return
            native_inputs = row.locator(ANSWER_INPUT_SELECTOR)
            if native_inputs.count():
                try:
                    self._set_native_input(native_inputs.first, selected)
                    if self._wait_until_state(row, selected):
                        return
                    last_error = BrowserStateError(
                        f"Native answer index {index} did not remain selected={selected}"
                    )
                except PlaywrightError as exc:
                    last_error = exc
                if attempt + 1 < self.settings.browser_max_retries:
                    time.sleep(2**attempt)
                continue
            try:
                row.scroll_into_view_if_needed()
                self._click_answer_control(row)
                if self._wait_until_state(row, selected):
                    return
                last_error = BrowserStateError(
                    f"Answer index {index} did not enter state selected={selected}"
                )
            except PlaywrightError as exc:
                last_error = exc
            label = row.locator(ANSWER_LABEL_DESCENDANT_SELECTOR)
            try:
                if label.count() and self._selected_state(row) is not selected:
                    self._click_answer_control(label.first)
                    if self._wait_until_state(row, selected):
                        return
                    last_error = BrowserStateError(
                        f"Answer index {index} did not enter state selected={selected}"
                    )
            except PlaywrightError as label_error:
                last_error = label_error
            if attempt + 1 < self.settings.browser_max_retries:
                time.sleep(2**attempt)
        raise BrowserStateError(
            f"Failed to set answer index {index} selected={selected}"
        ) from last_error

    @staticmethod
    def _selected_state(row: Locator) -> Optional[bool]:
        """Read a native or ARIA-backed selection state when detectable."""
        inputs = row.locator(ANSWER_INPUT_SELECTOR)
        if inputs.count():
            return any(inputs.nth(index).is_checked() for index in range(inputs.count()))
        aria_checked = (row.get_attribute("aria-checked") or "").casefold()
        if aria_checked in {"true", "false"}:
            return aria_checked == "true"
        data_state = (row.get_attribute("data-state") or "").casefold()
        if data_state in {"checked", "selected"}:
            return True
        if data_state in {"unchecked", "unselected"}:
            return False
        classes = (row.get_attribute("class") or "").casefold().split()
        if any(token in {"checked", "selected", "active"} for token in classes):
            return True
        return None

    def _wait_until_state(self, row: Locator, selected: bool) -> bool:
        page = self._require_page()
        for _ in range(10):
            if self._selected_state(row) is selected:
                return True
            page.wait_for_timeout(100)
        return False

    @staticmethod
    def _control_text(control: Locator) -> str:
        return str(
            control.evaluate(
                "el => el.value || el.getAttribute('aria-label') || el.textContent || ''"
            )
        ).strip()

    def _assert_safe_next(self, control: Locator) -> None:
        text = self._control_text(control)
        if is_final_submit_text(text):
            raise BrowserStateError(
                f"Refusing to click protected final-submit control: {text!r}"
            )

    def _next_button(self) -> Optional[Locator]:
        page = self._require_page()
        for text in NEXT_BUTTON_TEXTS:
            by_role = page.get_by_role("button", name=text, exact=False)
            if by_role.count():
                return by_role.first
            by_text = page.get_by_text(text, exact=False)
            if by_text.count():
                return by_text.first
        for selector in NEXT_CSS_SELECTORS:
            locator = page.locator(selector)
            if locator.count():
                return locator.first
        return None

    def go_next(self) -> bool:
        button = self._next_button()
        if button is None:
            return False
        self._assert_safe_next(button)
        last_error: Optional[BaseException] = None
        for attempt in range(self.settings.browser_max_retries):
            try:
                button.scroll_into_view_if_needed()
                button.click(timeout=self.settings.page_timeout_ms)
                return True
            except PlaywrightError as exc:
                last_error = exc
                if attempt + 1 < self.settings.browser_max_retries:
                    time.sleep(2**attempt)
                    button = self._next_button() or button
        raise BrowserStateError("Failed to click the Next button") from last_error

    def advance_to_next(self, old_question_id: str) -> Optional[Question]:
        """Click Next and retry the full click/change cycle a bounded number of times."""
        last_error: Optional[BaseException] = None
        for attempt in range(self.settings.browser_max_retries):
            if self.is_finished():
                return None
            if not self.go_next():
                return None
            try:
                return self.wait_for_question_change(old_question_id)
            except BrowserStateError as exc:
                last_error = exc
                if self.is_finished():
                    return None
                LOGGER.warning(
                    "Next-page attempt %d/%d did not change the question: %s",
                    attempt + 1,
                    self.settings.browser_max_retries,
                    exc,
                )
        raise BrowserStateError(
            "Page did not change after bounded Next-button retries"
        ) from last_error

    def wait_for_question_change(self, old_question_id: str) -> Question:
        page = self._require_page()

        def changed() -> bool:
            try:
                state = self.read_page_state()
                return state.finished or (
                    state.question is not None
                    and state.question.question_id != old_question_id
                )
            except (ExtractionError, PlaywrightError):
                return False

        try:
            page.wait_for_function(
                "() => document.readyState === 'interactive' || document.readyState === 'complete'",
                timeout=self.settings.page_timeout_ms,
            )
            page.wait_for_timeout(50)
            deadline = self.settings.page_timeout_ms
            elapsed = 0
            while elapsed < deadline:
                if changed():
                    state = self.read_page_state()
                    if state.finished:
                        raise BrowserStateError("Quiz reached the finish page")
                    assert state.question is not None
                    return state.question
                page.wait_for_timeout(200)
                elapsed += 200
        except PlaywrightTimeoutError as exc:
            raise BrowserStateError("Timed out waiting for the next question") from exc
        raise BrowserStateError("Page did not change after clicking next")

    def is_finished(self) -> bool:
        # Canvas may render a final-submit control throughout the attempt.
        # It is only a finish state when no safe Next control remains.
        return self._final_submit_control() is not None and self._next_button() is None

    def has_final_submit_control(self) -> bool:
        """Report presence separately from the finish-state decision."""
        return self._final_submit_control() is not None

    def _final_submit_control(self) -> Optional[Locator]:
        page = self._require_page()
        for text in FINAL_SUBMIT_TEXTS:
            if page.get_by_role("button", name=text, exact=False).count():
                return page.get_by_role("button", name=text, exact=False).first
            if page.get_by_role("link", name=text, exact=False).count():
                return page.get_by_role("link", name=text, exact=False).first
        for selector in FINAL_CONTROL_SELECTORS:
            controls = page.locator(selector)
            for index in range(controls.count()):
                control = controls.nth(index)
                if is_final_submit_text(self._control_text(control)):
                    return control
        return None

    def debug_current_question(self) -> None:
        page = self._require_page()
        LOGGER.info("Current URL: %s", self._safe_url(page.url))
        LOGGER.info("Open pages: %d | Frames on selected page: %d", len(self._context.pages) if self._context else 1, len(page.frames))
        diagnostics = QuestionExtractor(page).diagnostics()
        LOGGER.info("question_text matches: %d", diagnostics.question_matches)
        LOGGER.info("Question ID: %s", diagnostics.question_id)
        LOGGER.info("Question Text: %s", diagnostics.question_text)
        LOGGER.info("Option count: %d", diagnostics.answer_matches)
        for index, answer in enumerate(diagnostics.answers):
            LOGGER.info("Option [%d]: %s", index, answer)
        LOGGER.info("Question type: %s", diagnostics.question_type)
        LOGGER.info("Next button found: %s", self._next_button() is not None)
        LOGGER.info("Final submit button found: %s", self.has_final_submit_control())
        LOGGER.info("Finish state detected: %s", self.is_finished())

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except PlaywrightError:
                LOGGER.debug("Browser context was already closed", exc_info=True)
        if self._browser is not None:
            try:
                self._browser.close()
            except PlaywrightError:
                LOGGER.debug("Browser was already closed", exc_info=True)
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except PlaywrightError:
                LOGGER.debug("Playwright was already stopped", exc_info=True)

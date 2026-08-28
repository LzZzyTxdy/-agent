"""All site-specific DOM selectors and button text fallbacks."""

QUESTION_TEXT_SELECTORS = [
    'textarea[name="question_text"]',
    '.original_question_text textarea[name="question_text"]',
    '.display_question .question_text',
    '[data-role="question-text"]',
    '.question_text',
]

QUESTION_PAGE_URL_MARKERS = ["/take/questions/", "/take/questions"]

ANSWER_LABEL_SELECTORS = [
    ".answers .answer_label",
    ".answers label .answer_label",
    '[data-role="answer-label"]',
]

ANSWER_ROW_SELECTORS = [
    ".answers .answer",
    '[data-role="answer"]',
]

ANSWER_INPUT_SELECTOR = 'input[type="radio"], input[type="checkbox"]'
ANSWER_LABEL_DESCENDANT_SELECTOR = "label"
ANSWER_TYPE_INPUT_SELECTOR = (
    '.answers input[type="checkbox"], .answers input[type="radio"]'
)

QUESTION_CONTAINER_SELECTORS = [
    '[id^="question_"]',
    ".question",
    '[data-question-id]',
]

NEXT_BUTTON_TEXTS = ["下一页", "下一题", "下一个", "Next"]

FINAL_SUBMIT_TEXTS = [
    "完成",
    "结束测试",
    "提交所有答案",
    "提交测验",
    "提交答案",
    "结束并提交",
    "结束作答",
    "提交试卷",
    "交卷",
    "Submit Quiz",
    "Submit all",
    "Finish attempt",
]

FINAL_CONTROL_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button[name*="submit" i]',
    '[data-action*="submit" i]',
    'a[role="button"]',
]

NEXT_CSS_SELECTORS = [
    "button.next-question",
    "button.submit_button.next-question",
    'button[name="next"]',
    'input[name="next"]',
    '[data-action="next"]',
    'button.next',
    'input.next',
]


def is_final_submit_text(value: str) -> bool:
    """Return whether control text represents a protected final submission."""
    normalized = " ".join(value.split()).casefold()
    for text in FINAL_SUBMIT_TEXTS:
        protected = text.casefold()
        if protected == "完成":
            if normalized == protected:
                return True
        elif protected in normalized:
            return True
    return False

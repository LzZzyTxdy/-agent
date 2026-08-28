"""Bounded state-machine orchestration for the quiz workflow."""

import logging
from enum import Enum
from typing import Set, Tuple

from browser import BrowserController
from config import Settings
from exceptions import BrowserStateError
from models import AnswerDecision, Question
from policy import DecisionPolicy, ManualAction
from solver import Solver
from storage import QuestionCache, RunRecorder

LOGGER = logging.getLogger(__name__)


class AgentState(str, Enum):
    INIT = "INIT"
    READ = "READ"
    CHECK_CACHE = "CHECK_CACHE"
    SOLVE = "SOLVE"
    VALIDATE = "VALIDATE"
    SELECT = "SELECT"
    RECORD = "RECORD"
    NEXT = "NEXT"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


class QuizAgent:
    def __init__(
        self,
        settings: Settings,
        browser: BrowserController,
        solver: Solver,
        policy: DecisionPolicy,
        cache: QuestionCache,
        recorder: RunRecorder,
    ) -> None:
        self.settings = settings
        self.browser = browser
        self.solver = solver
        self.policy = policy
        self.cache = cache
        self.recorder = recorder
        self.answered_question_ids: Set[str] = set()
        self.state = AgentState.INIT

    def _show(self, number: int, question: Question, decision: AnswerDecision, source: str) -> None:
        LOGGER.info("=" * 60)
        LOGGER.info("Question #%d | ID: %s", number, question.question_id)
        LOGGER.info("%s", question.text)
        for index, option in enumerate(question.options):
            LOGGER.info("[%d] %s", index, option)
        selected_answers = [
            question.options[index] for index in decision.choice_indices
        ]
        LOGGER.info(
            "Decision (%s): choice=%s answer=%s confidence=%.2f",
            source,
            decision.choice,
            " | ".join(selected_answers),
            decision.confidence,
        )
        LOGGER.info("Reason: %s", decision.reason)
        if decision.sources:
            LOGGER.info("Sources: %s", " | ".join(decision.sources))

    def _decision(self, question: Question) -> Tuple[AnswerDecision, str]:
        self.state = AgentState.CHECK_CACHE
        cached = self.cache.get(question)
        if cached is not None and cached.confidence >= self.settings.min_confidence:
            self.policy.validate(question, cached)
            return cached, "cache"
        self.state = AgentState.SOLVE
        raw = self.solver.solve(question)
        self.state = AgentState.VALIDATE
        decision = self.policy.apply(
            question,
            raw,
            lambda: self.solver.solve(question),
            defer_manual=(
                self.settings.agent_mode == "manual"
                or self.settings.low_confidence_mode == "manual"
            ),
        )
        if decision.confidence >= self.settings.min_confidence:
            self.cache.put(question, decision)
        return decision, "llm" if self.settings.solver_type == "llm" else "mock"

    def _record_error(self, question_id: str, exc: BaseException) -> None:
        self.recorder.append(
            {"question_id": question_id, "status": "error", "error": str(exc)}
        )

    def run(self) -> None:
        # The bound prevents a malformed site from creating an unbounded click loop.
        for number in range(1, 1001):
            self.state = AgentState.READ
            state = self.browser.read_page_state()
            if state.finished:
                self.state = AgentState.FINISHED
                self._log_finished()
                return
            assert state.question is not None
            question = state.question
            try:
                if question.question_id in self.answered_question_ids:
                    LOGGER.warning("Question already answered; retrying Next once.")
                    next_question = self.browser.advance_to_next(question.question_id)
                    if next_question is None:
                        self.state = AgentState.FINISHED
                        self._log_finished()
                        return
                    continue

                decision, source = self._decision(question)
                self._show(number, question, decision, source)
                if self.settings.agent_mode == "dry_run":
                    LOGGER.info("dry_run: no browser click was performed.")
                    return

                needs_manual_review = (
                    self.settings.agent_mode == "manual"
                    or (
                        decision.confidence < self.settings.min_confidence
                        and self.settings.low_confidence_mode == "manual"
                    )
                )
                if needs_manual_review:
                    review = self.policy.manual_review(question, decision)
                    if review.action is ManualAction.QUIT:
                        LOGGER.info("用户停止了 Agent；页面未被点击。")
                        return
                    if review.action is ManualAction.SKIP:
                        self.recorder.append(
                            {
                                "question_id": question.question_id,
                                "question": question.text,
                                "options": question.options,
                                "source": source + "+manual",
                                "status": "skipped",
                            }
                        )
                        next_question = self.browser.advance_to_next(
                            question.question_id
                        )
                        if next_question is None:
                            self.state = AgentState.FINISHED
                            self._log_finished()
                            return
                        continue
                    assert review.decision is not None
                    decision = review.decision
                    source += "+manual"

                self.state = AgentState.SELECT
                selected_indices = self.browser.select_answers(
                    decision.choice_indices,
                    option_count=len(question.options),
                    multiple=question.question_type == "multiple_choice",
                )
                LOGGER.info(
                    "Action: selected choices=%s answers=%s",
                    selected_indices,
                    " | ".join(
                        question.options[index] for index in selected_indices
                    ),
                )
                self.answered_question_ids.add(question.question_id)
                self.state = AgentState.RECORD
                self.recorder.append(
                    {
                        "question_id": question.question_id,
                        "question": question.text,
                        "options": question.options,
                        "choice": decision.choice,
                        "selected_indices": selected_indices,
                        "selected_answer": (
                            [
                                question.options[index]
                                for index in selected_indices
                            ]
                            if question.question_type == "multiple_choice"
                            else question.options[selected_indices[0]]
                        ),
                        "confidence": decision.confidence,
                        "reason": decision.reason,
                        "sources": decision.sources,
                        "source": source,
                        "status": "answered",
                    }
                )
                self.state = AgentState.NEXT
                next_question = self.browser.advance_to_next(question.question_id)
                if next_question is None:
                    self.state = AgentState.FINISHED
                    self._log_finished()
                    return
            except Exception as exc:
                self.state = AgentState.ERROR
                self._record_error(question.question_id, exc)
                raise
        raise BrowserStateError("Safety limit of 1000 questions reached")

    @staticmethod
    def _log_finished() -> None:
        LOGGER.info("=" * 48)
        LOGGER.info("检测到测试结束/最终提交页面。")
        LOGGER.info("所有题目处理完成。Agent 已停止。")
        LOGGER.info("为避免误操作，最终提交不会自动执行。")
        LOGGER.info("请在浏览器中人工检查答案并手动决定是否提交。")
        LOGGER.info("=" * 48)

"""Command-line entry point for the quiz agent."""

import argparse
import logging
import sys
from typing import Optional

from agent import QuizAgent
from browser import BrowserController
from config import Settings
from policy import DecisionPolicy
from solver import LLMSolver, MockSolver
from storage import QuestionCache, RunRecorder
from models import Question
from retrieval import RetrievalManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DOM-driven quiz answer agent")
    parser.add_argument(
        "--debug-dom",
        action="store_true",
        help="inspect current question without calling the solver or clicking",
    )
    parser.add_argument(
        "--test-retrieval",
        nargs="?",
        const="论文评阅书存在异议的情形",
        metavar="QUERY",
        help="search local PDFs and optional web sources without starting a browser",
    )
    parser.add_argument(
        "--test-llm",
        action="store_true",
        help="call the configured LLM once without starting a browser",
    )
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def test_llm(settings: Settings) -> int:
    """Run a browser-free connectivity and structured-output smoke test."""
    solver = LLMSolver(settings, force=True, retrieval_enabled=False)
    question = Question(
        question_id="llm-smoke-test",
        text="2 + 2 等于多少？",
        options=["3", "4", "5"],
    )
    decision = solver.solve(question)
    DecisionPolicy.validate(question, decision)
    logging.getLogger(__name__).info("LLM connection: OK")
    logging.getLogger(__name__).info("Model: %s", settings.llm_model)
    logging.getLogger(__name__).info("Choice: %d", decision.choice)
    logging.getLogger(__name__).info("Confidence: %.2f", decision.confidence)
    logging.getLogger(__name__).info("Reason: %s", decision.reason)
    if decision.choice != 1:
        logging.getLogger(__name__).error(
            "LLM smoke test returned an unexpected choice; expected 1."
        )
        return 1
    return 0


def test_retrieval(settings: Settings, query: str) -> int:
    """Run retrieval tools without calling the LLM or opening a browser."""
    question = Question(
        question_id="retrieval-smoke-test",
        text=query,
        options=["检索测试"],
    )
    manager = RetrievalManager(settings)
    evidence = manager.retrieve(question)
    logger = logging.getLogger(__name__)
    logger.info("Retrieval results: %d", len(evidence))
    for index, item in enumerate(evidence, start=1):
        logger.info(
            "[%d] kind=%s score=%.2f source=%s",
            index,
            item.kind,
            item.score,
            item.source,
        )
        logger.info("    %s", item.content[:300])
    return 0 if evidence else 1


def main() -> int:
    configure_logging()
    args = parse_args()
    settings = Settings()
    browser: Optional[BrowserController] = None
    try:
        if args.test_llm:
            return test_llm(settings)
        if args.test_retrieval is not None:
            return test_retrieval(settings, args.test_retrieval)
        browser = BrowserController(settings)
        browser.start()
        browser.wait_for_user_login()
        if args.debug_dom:
            browser.debug_current_question()
            return 0
        solver = (
            MockSolver(settings.mock_mode)
            if settings.solver_type == "mock"
            else LLMSolver(settings)
        )
        agent = QuizAgent(
            settings=settings,
            browser=browser,
            solver=solver,
            policy=DecisionPolicy(
                settings.min_confidence, settings.low_confidence_mode
            ),
            cache=QuestionCache(settings.cache_path),
            recorder=RunRecorder(settings.runs_dir),
        )
        agent.run()
        if agent.state.value == "FINISHED":
            browser.wait_for_manual_final_review()
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        logging.getLogger(__name__).error("Agent stopped: %s", exc)
        return 1
    finally:
        if browser is not None:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())

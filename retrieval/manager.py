"""Retrieval policy combining trusted local references and web snippets."""

import logging
from typing import List

from config import PROJECT_DIR, Settings
from models import Question
from retrieval.local_pdf import LocalPdfRetriever
from retrieval.models import Evidence
from retrieval.web_search import WebSearchRetriever

LOGGER = logging.getLogger(__name__)


class RetrievalManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.local = LocalPdfRetriever(
            project_dir=PROJECT_DIR,
            pdf_glob=settings.reference_pdf_glob,
            index_path=settings.pdf_index_path,
            chunk_chars=settings.retrieval_chunk_chars,
        )
        self.web = WebSearchRetriever(
            cache_path=settings.web_search_cache_path,
            timeout_seconds=settings.web_search_timeout_seconds,
            backend=settings.web_search_backend,
        )

    @staticmethod
    def query_for(question: Question) -> str:
        return "\n".join([question.text, *question.options])

    def retrieve(self, question: Question) -> List[Evidence]:
        local_results: List[Evidence] = []
        if self.settings.enable_local_retrieval:
            local_results = self.local.search(
                self.query_for(question), self.settings.retrieval_top_k
            )
        best_local_score = local_results[0].score if local_results else 0.0
        evidence = [
            item
            for item in local_results
            if item.score >= self.settings.local_retrieval_min_score
        ]
        should_search_web = self.settings.web_search_mode == "always" or (
            self.settings.web_search_mode == "auto"
            and best_local_score < self.settings.local_retrieval_min_score
        )
        if should_search_web:
            web_query = question.text[:350]
            web_results = self.web.search(
                web_query, self.settings.web_search_max_results
            )
            evidence.extend(web_results)
        LOGGER.info(
            "Retrieval: local=%d web=%d best_local_score=%.2f",
            sum(item.kind == "local_pdf" for item in evidence),
            sum(item.kind == "web_search" for item in evidence),
            best_local_score,
        )
        return evidence

    def context(self, evidence: List[Evidence]) -> str:
        blocks: List[str] = []
        length = 0
        for number, item in enumerate(evidence, start=1):
            block = item.prompt_text(number)
            remaining = self.settings.retrieval_max_context_chars - length
            if remaining <= 0:
                break
            block = block[:remaining]
            blocks.append(block)
            length += len(block)
        return "\n\n".join(blocks)

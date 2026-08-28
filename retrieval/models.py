"""Evidence model shared by retrieval tools and the LLM solver."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    source: str
    title: str
    content: str
    score: float
    kind: str

    def prompt_text(self, number: int) -> str:
        return (
            f"[资料{number} | {self.kind} | {self.source}]\n"
            f"标题：{self.title}\n内容：{self.content}"
        )

from typing import Protocol


class SimilarityDetector(Protocol):
    def score(self, text: str) -> float:
        ...


class AIGCDetector(Protocol):
    def score(self, text: str) -> float:
        ...


class Rewriter(Protocol):
    async def rewrite(
        self,
        text: str,
        topic_hint: str | None = None,
        preserve_terms: list[str] | None = None,
        model_name: str | None = None,
        enable_reasoning: bool = True,
    ) -> str:
        ...

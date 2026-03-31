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
        global_context: str | None = None,
        aigc_reduction_strategy: str | None = None,
        enable_structural_rebuild: bool = False,
    ) -> str:
        ...

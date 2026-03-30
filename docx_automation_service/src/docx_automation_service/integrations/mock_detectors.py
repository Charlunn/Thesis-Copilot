import re

from docx_automation_service.integrations.base import AIGCDetector, SimilarityDetector


class HeuristicSimilarityDetector(SimilarityDetector):
    """Lightweight plagiarism risk heuristic (NOT PRODUCTION-GRADE).
    
    Scores based on n-gram uniqueness ratio. High unique diversity → lower risk.
    Replace with Turnitin/Copyleaks/Grammarly API for production use.
    """

    def score(self, text: str) -> float:
        words = re.findall(r"\w+", text.lower())
        if len(words) < 20:
            return 0.0

        n = 8
        grams = [" ".join(words[i : i + n]) for i in range(0, max(0, len(words) - n + 1))]
        if not grams:
            return 0.0

        unique_ratio = len(set(grams)) / len(grams)
        return float(max(0.0, min(1.0, 1.0 - unique_ratio)))


class HeuristicAIGCDetector(AIGCDetector):
    """Lightweight AIGC risk heuristic using perplexity/burstiness proxy signals (NOT PRODUCTION-GRADE).
    
    Scores based on:
    - Low variance in sentence lengths (low burstiness)
    - High frequency of transition words (AI markers)
    Replace with Copyleaks/Turnitin/GPTZero API for production use.
    """

    TRANSITIONS = {"此外", "总而言之", "值得注意的是", "therefore", "furthermore", "in conclusion"}

    def score(self, text: str) -> float:
        parts = [p.strip() for p in re.split(r"[。！？.!?]", text) if p.strip()]
        if len(parts) < 3:
            return 0.0

        lengths = [len(p) for p in parts]
        avg = sum(lengths) / len(lengths)
        var = sum((x - avg) ** 2 for x in lengths) / len(lengths)
        low_burstiness = max(0.0, 1.0 - min(var / 150.0, 1.0))

        lowered = text.lower()
        transition_hits = sum(1 for t in self.TRANSITIONS if t in lowered)
        transition_score = min(1.0, transition_hits / 4.0)

        return float(min(1.0, 0.65 * low_burstiness + 0.35 * transition_score))

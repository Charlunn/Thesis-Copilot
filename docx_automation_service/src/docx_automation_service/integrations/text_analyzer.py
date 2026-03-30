"""Layer 3 – AI-Feature Elimination via Perplexity & Burstiness Analysis.

AI detectors such as GPTZero and Turnitin primarily detect text *predictability*:
- **Perplexity proxy**: highly uniform sentence complexity → likely AI.
- **Burstiness**: low variance in sentence lengths → likely AI.

This module:
1. Analyzes text with ``textstat`` (when installed) for readability metrics.
2. Computes a *burstiness score* from sentence-length variance.
3. Injects short, punchy sentences into low-burstiness text to mimic the
   natural rhythm of human academic writing.

Inspired by the ``gpt-zero-buster`` algorithm and the ``textstat`` library.
``textstat`` is an **optional** dependency; all functions degrade gracefully
when it is unavailable.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    import textstat as _textstat  # type: ignore[import-untyped]

    _TEXTSTAT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _textstat = None  # type: ignore[assignment]
    _TEXTSTAT_AVAILABLE = False
    logger.warning(
        "textstat not installed; text complexity analysis will use built-in heuristics. "
        "Install with: pip install textstat"
    )


# ---------------------------------------------------------------------------
# Short sentence injections used for burstiness boosting
# ---------------------------------------------------------------------------

_INJECTIONS_ZH: list[str] = [
    "这一点至关重要。",
    "值得深思。",
    "实验结果证明了这一点。",
    "这并不简单。",
    "问题的关键在此。",
    "后文将详细说明。",
    "这是一个关键约束。",
    "方案需要权衡。",
    "系统必须适应这种情况。",
    "这需要进一步验证。",
]

_INJECTIONS_EN: list[str] = [
    "This is critical.",
    "The results confirm this.",
    "Further validation is needed.",
    "This constraint shapes the design.",
    "The trade-off is significant.",
    "Implementation reveals the challenge.",
    "Testing exposed this limitation.",
    "We reconsidered the approach.",
    "The system adapts accordingly.",
    "This is non-trivial.",
]

# Transition words that are strong indicators of AI-generated text.
_AI_TRANSITION_WORDS: frozenset[str] = frozenset(
    {
        # Chinese
        "此外",
        "总而言之",
        "值得注意的是",
        "不可避免地",
        "由此产生",
        "综上所述",
        "不言而喻",
        # English
        "furthermore",
        "in conclusion",
        "it is worth noting",
        "therefore",
        "moreover",
        "notably",
        "inevitably",
    }
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TextComplexityReport:
    """Detailed text-complexity metrics for AI-detection risk assessment."""

    sentence_count: int
    avg_sentence_length: float
    sentence_length_variance: float
    burstiness_score: float
    """0 = very low (AI-like uniform rhythm), 1 = very high (human-like varied)."""
    ai_transition_density: float
    """Fraction of detected AI transition words relative to sentence count."""
    flesch_reading_ease: float
    flesch_kincaid_grade: float
    gunning_fog: float
    needs_burstiness_injection: bool
    """*True* when burstiness is low enough to warrant intervention."""
    layer3_risk_score: float
    """Composite 0–1 risk score; higher = more likely AI-generated."""
    metrics: dict[str, float] = field(default_factory=dict)
    """Raw metric dictionary for downstream reporting."""


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on Chinese and ASCII punctuation."""
    parts = [p.strip() for p in re.split(r"[。！？.!?；;]+", text) if p.strip()]
    return parts


def _sentence_length_variance(sentences: list[str]) -> float:
    """Variance of character counts across *sentences*."""
    if len(sentences) < 2:
        return 0.0
    lengths = [len(s) for s in sentences]
    avg = sum(lengths) / len(lengths)
    return sum((x - avg) ** 2 for x in lengths) / len(lengths)


def analyze_text(text: str) -> TextComplexityReport:
    """Compute burstiness, readability, and AI-risk metrics for *text*.

    Works on both Chinese and English text.  ``textstat`` metrics are only
    meaningful for English, but the burstiness and transition-density signals
    are language-agnostic.
    """
    sentences = _split_sentences(text)
    n = len(sentences)

    if n == 0:
        return TextComplexityReport(
            sentence_count=0,
            avg_sentence_length=0.0,
            sentence_length_variance=0.0,
            burstiness_score=0.5,
            ai_transition_density=0.0,
            flesch_reading_ease=0.0,
            flesch_kincaid_grade=0.0,
            gunning_fog=0.0,
            needs_burstiness_injection=False,
            layer3_risk_score=0.0,
        )

    variance = _sentence_length_variance(sentences)
    avg_len = sum(len(s) for s in sentences) / n

    # Burstiness: normalise variance to [0, 1].
    # Typical human Chinese academic writing: variance 150–500.
    # AI tends to cluster around 50–120.
    burstiness_score = float(min(1.0, variance / 300.0))

    # AI transition word density
    lowered = text.lower()
    hits = sum(1 for t in _AI_TRANSITION_WORDS if t in lowered)
    transition_density = float(min(1.0, hits / max(1, n)))

    # textstat metrics (English-centric; use zero-fallback for Chinese)
    if _TEXTSTAT_AVAILABLE and _textstat is not None:
        try:
            flesch_ease = float(_textstat.flesch_reading_ease(text))
            fk_grade = float(_textstat.flesch_kincaid_grade(text))
            fog = float(_textstat.gunning_fog(text))
        except Exception:  # noqa: BLE001
            flesch_ease, fk_grade, fog = 50.0, 10.0, 12.0
    else:
        words = re.findall(r"\w+", text)
        avg_word_len = sum(len(w) for w in words) / max(1, len(words))
        flesch_ease = max(0.0, 100.0 - avg_len * 0.5 - avg_word_len * 2.0)
        fk_grade = min(20.0, avg_len / 5.0 + avg_word_len * 0.5)
        fog = min(20.0, (avg_len + avg_word_len) * 0.4)

    # Composite risk: weight burstiness most heavily
    layer3_risk = float(
        min(1.0, 0.55 * (1.0 - burstiness_score) + 0.45 * transition_density)
    )

    needs_injection = burstiness_score < 0.3 and n >= 3

    return TextComplexityReport(
        sentence_count=n,
        avg_sentence_length=avg_len,
        sentence_length_variance=variance,
        burstiness_score=burstiness_score,
        ai_transition_density=transition_density,
        flesch_reading_ease=flesch_ease,
        flesch_kincaid_grade=fk_grade,
        gunning_fog=fog,
        needs_burstiness_injection=needs_injection,
        layer3_risk_score=layer3_risk,
        metrics={
            "sentence_count": float(n),
            "avg_sentence_length": avg_len,
            "variance": variance,
            "burstiness_score": burstiness_score,
            "transition_density": transition_density,
            "flesch_reading_ease": flesch_ease,
            "flesch_kincaid_grade": fk_grade,
            "gunning_fog": fog,
            "layer3_risk_score": layer3_risk,
        },
    )


# ---------------------------------------------------------------------------
# Burstiness injection
# ---------------------------------------------------------------------------


def inject_burstiness(
    text: str,
    lang: str = "zh",
    min_long_run: int = 3,
) -> str:
    """Insert short sentences to increase sentence-length variance.

    After every *min_long_run* consecutive sentences that are longer than the
    paragraph average, a short punchy sentence is inserted.  This mimics the
    natural rhythm of human academic writing and lowers AI-detection risk by
    increasing the *burstiness* signal measured by tools like GPTZero.

    Args:
        text:         Input text (Chinese or English paragraph).
        lang:         ``'zh'`` or ``'en'`` – selects the injection phrase bank.
        min_long_run: Consecutive long sentences before an injection is made.

    Returns:
        Text with burstiness-enhancing sentence injections.  If fewer than
        *min_long_run* sentences exist the original text is returned unchanged.
    """
    sentences = _split_sentences(text)
    if len(sentences) < min_long_run + 1:
        return text

    injections = _INJECTIONS_ZH if lang == "zh" else _INJECTIONS_EN
    avg_len = sum(len(s) for s in sentences) / len(sentences)
    long_threshold = avg_len * 1.1  # 110 % of average counts as "long"

    result_parts: list[str] = []
    injection_idx = 0
    consecutive_long = 0

    for sentence in sentences:
        result_parts.append(sentence)
        if len(sentence) >= long_threshold:
            consecutive_long += 1
            if consecutive_long >= min_long_run:
                result_parts.append(injections[injection_idx % len(injections)])
                injection_idx += 1
                consecutive_long = 0
        else:
            consecutive_long = 0

    # Re-join with appropriate sentence terminator
    if lang == "zh":
        # Strip trailing punctuation from each part then rejoin with 。
        clean = [s.rstrip("。！？.!?；;") for s in result_parts]
        return "。".join(clean) + "。"
    else:
        return " ".join(result_parts)

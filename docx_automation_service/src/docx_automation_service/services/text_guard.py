from __future__ import annotations

import logging
import re

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_MARKDOWN_FENCE_RE = re.compile(r"```(?:[\w-]+)?\n.*?```", re.DOTALL)
_HEADING_RE = re.compile(r"^(?:第[0-9一二三四五六七八九十百千]+章\s*.+|\d+(?:\.\d+){1,4}\s+.+)$")
_STRATEGY_LINE_RE = re.compile(r"^第[0-9一二三四五六七八九十]+个策略")

# ---------------------------------------------------------------------------
# Entity hallucination detection patterns
# ---------------------------------------------------------------------------
_PERCENTAGE_RE = re.compile(r"\d+(?:\.\d+)?%")
_CITATION_BRACKET_RE = re.compile(r"\[\d+\]")
_CITATION_AUTHOR_RE = re.compile(r"\([A-Za-z][A-Za-z\s,\.]+,?\s*\d{4}\)")
_DECIMAL_NUMBER_RE = re.compile(r"\b\d+\.\d+\b")

logger = logging.getLogger(__name__)

_REASONING_MARKERS = (
    "我现在需要",
    "我得",
    "首先",
    "接下来",
    "然后",
    "现在来看",
    "最后",
    "总的来说",
    "总之",
    "我还需要注意",
    "另外，要注意",
    "在改写过程中",
    "这可以让改写后的文本",
    "用户明确列出",
    "用户",
    "核心策略",
)


def check_entity_hallucination(generated_text: str, source_text: str) -> bool:
    """Return True if *generated_text* introduces numeric/citation entities absent from *source_text*.

    Extracts percentages, bracket citations, author-year citations, and decimal
    numbers from the generated text.  If any such entity is present in the
    generated text but **completely absent** from the source text it is
    considered a hallucination and this function returns ``True``.
    """
    for pattern in (
        _PERCENTAGE_RE,
        _CITATION_BRACKET_RE,
        _CITATION_AUTHOR_RE,
        _DECIMAL_NUMBER_RE,
    ):
        gen_matches = set(pattern.findall(generated_text))
        if not gen_matches:
            continue
        src_matches = set(pattern.findall(source_text))
        hallucinated = gen_matches - src_matches
        if hallucinated:
            logger.warning(
                "entity hallucination detected | pattern=%s | new_entities=%s",
                pattern.pattern,
                hallucinated,
            )
            return True
    return False


def sanitize_model_output(text: str, *, original_text: str, source_is_heading: bool) -> str:
    """Remove leaked reasoning/meta text and heading-like pollution.

    Also performs entity hallucination detection: if the generated text
    introduces numeric data, percentages, or citation markers that are absent
    from the original source, the original text is returned as a fallback.

    Returns the original text if sanitization strips everything useful.
    """
    candidate = text.strip()
    if not candidate:
        return original_text

    candidate = _THINK_BLOCK_RE.sub("", candidate)
    candidate = _MARKDOWN_FENCE_RE.sub("", candidate)

    lines: list[str] = []
    for raw in candidate.splitlines():
        line = raw.strip()
        if not line:
            continue

        if line.startswith("#"):
            continue

        if _looks_like_reasoning_line(line):
            continue

        if not source_is_heading and _HEADING_RE.match(line):
            continue

        lines.append(line)

    cleaned = "\n".join(lines).strip()
    if not cleaned:
        return original_text

    if check_entity_hallucination(cleaned, original_text):
        logger.warning("entity hallucination guard triggered; falling back to original text")
        return original_text

    return cleaned


def is_heading_like(text: str, style_name: str | None = None) -> bool:
    line = text.strip().splitlines()[0] if text.strip() else ""
    if _HEADING_RE.match(line):
        return True

    style = (style_name or "").strip().lower()
    if not style:
        return False
    return "heading" in style or "标题" in style


def split_for_rewrite(text: str, *, target_chars: int, max_chars: int) -> list[str]:
    """Split long text into sentence-aware chunks for slower reasoning models."""
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return [stripped]

    pieces = re.split(r"(?<=[。！？!?；;])", stripped)
    chunks: list[str] = []
    current = ""

    for piece in pieces:
        part = piece.strip()
        if not part:
            continue

        if len(part) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(part, max_chars))
            continue

        if not current:
            current = part
            continue

        if len(current) + len(part) <= target_chars:
            current += part
        else:
            chunks.append(current)
            current = part

    if current:
        chunks.append(current)

    return chunks or [stripped]


def _hard_split(text: str, max_chars: int) -> list[str]:
    out: list[str] = []
    start = 0
    while start < len(text):
        out.append(text[start:start + max_chars])
        start += max_chars
    return out


def _looks_like_reasoning_line(line: str) -> bool:
    if line.startswith("<") and line.endswith(">"):
        return True

    if _STRATEGY_LINE_RE.match(line):
        return True

    for marker in _REASONING_MARKERS:
        if line.startswith(marker):
            return True

    lowered = line.lower()
    if "need to" in lowered and "rewrite" in lowered:
        return True
    if "用户" in line and ("改写" in line or "文本" in line):
        return True
    if "黑名单词汇" in line:
        return True

    return False

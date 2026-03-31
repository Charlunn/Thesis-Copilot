from __future__ import annotations

import logging
import re

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_MARKDOWN_FENCE_RE = re.compile(r"```(?:[\w-]+)?\n.*?```", re.DOTALL)
_HEADING_RE = re.compile(r"^(?:第[0-9一二三四五六七八九十百千]+章\s*.+|\d+(?:\.\d+){1,4}\s+.+)$")
_STRATEGY_LINE_RE = re.compile(r"^第[0-9一二三四五六七八九十]+个策略")

# ---------------------------------------------------------------------------
# Guard Token constants and patterns
# ---------------------------------------------------------------------------
_GUARD_PREFIX = "[[GUARD_TOKEN_"
_GUARD_SUFFIX = "]]"
_GUARD_TOKEN_RE = re.compile(r"\[\[GUARD_TOKEN_\d{3}\]\]")

# Patterns for entities that must survive LLM processing intact
# Applied in order from most-specific to least-specific to avoid partial overlap
_PROTECT_TAG_RE = re.compile(r"<[A-Za-z][A-Za-z0-9_]*(?:\s[^<>]*)?>")
_PROTECT_CITATION_BRACKET_RE = re.compile(r"\[\d+(?:[,，\s]+\d+)*\]")
_PROTECT_CITATION_AUTHOR_RE = re.compile(r"\([A-Z][A-Za-z\s,\.&]+,?\s*\d{4}[a-z]?\)")
_PROTECT_ENGLISH_NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b")
_PROTECT_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")

_REFERENCES_HEADER_RE = re.compile(
    r"^(?:参考文献|References|Bibliography)\s*$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Guard Context: protect sensitive entities during LLM processing
# ---------------------------------------------------------------------------


class GuardContext:
    """Extract → placeholder → restore mechanism for sensitive text entities.

    Protects XML/HTML-like tags (``<role>``), bracket citations (``[1]``),
    author-year citations (``(Doe, 2024)``), English proper names, and years
    from being modified or dropped by the LLM.  Reference-only paragraphs are
    detected separately via :func:`is_references_section`.

    Usage::

        ctx = GuardContext()
        protected, token_map = ctx.protect(text)
        # … send *protected* to the LLM …
        restored = ctx.restore(llm_output, token_map)
    """

    def protect(self, text: str) -> tuple[str, dict[str, str]]:
        """Replace sensitive entities with opaque guard tokens.

        Returns ``(protected_text, token_map)`` where *token_map* maps each
        ``[[GUARD_TOKEN_NNN]]`` back to the original string it replaced.
        """
        token_map: dict[str, str] = {}
        counter = [0]

        def _make_token(original: str) -> str:
            idx = counter[0]
            counter[0] += 1
            token = f"{_GUARD_PREFIX}{idx:03d}{_GUARD_SUFFIX}"
            token_map[token] = original
            return token

        result = text

        # Apply patterns from most-specific to least-specific so that later
        # patterns cannot match inside an already-tokenised span.
        result = _PROTECT_TAG_RE.sub(lambda m: _make_token(m.group()), result)
        result = _PROTECT_CITATION_BRACKET_RE.sub(lambda m: _make_token(m.group()), result)
        result = _PROTECT_CITATION_AUTHOR_RE.sub(lambda m: _make_token(m.group()), result)
        result = _PROTECT_ENGLISH_NAME_RE.sub(lambda m: _make_token(m.group()), result)
        result = _PROTECT_YEAR_RE.sub(lambda m: _make_token(m.group()), result)

        return result, token_map

    @staticmethod
    def restore(text: str, token_map: dict[str, str]) -> str:
        """Replace every guard token in *text* with its original string."""
        result = text
        for token, original in token_map.items():
            result = result.replace(token, original)
        return result

    @staticmethod
    def count_tokens(text: str, token_map: dict[str, str]) -> int:
        """Return the number of guard tokens from *token_map* present in *text*."""
        return sum(1 for token in token_map if token in text)


def is_references_section(text: str) -> bool:
    """Return ``True`` if *text* is a references/bibliography block.

    A chunk is treated as a references section when its **first non-empty
    line** matches the known section headers (参考文献, References,
    Bibliography).  Such chunks should be passed through unchanged without LLM
    processing.
    """
    stripped = text.strip()
    if not stripped:
        return False
    first_line = stripped.splitlines()[0].strip()
    return bool(_REFERENCES_HEADER_RE.match(first_line))


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

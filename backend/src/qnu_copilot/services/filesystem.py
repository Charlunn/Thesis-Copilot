from __future__ import annotations

import hashlib
import re
from pathlib import Path

from qnu_copilot.services.errors import InvalidInputError


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
MULTI_WHITESPACE = re.compile(r"\s+")
MATCH_KEY_FILTER = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
MAX_TITLE_LENGTH = 120


def sanitize_title(title: str, max_length: int = MAX_TITLE_LENGTH) -> str:
    sanitized = INVALID_FILENAME_CHARS.sub("", title)
    sanitized = MULTI_WHITESPACE.sub(" ", sanitized).strip(" .")
    if not sanitized:
        sanitized = "untitled"
    return sanitized[:max_length].rstrip(" .") or "untitled"


def normalize_lookup_key(title: str) -> str:
    sanitized = sanitize_title(title).lower()
    return MATCH_KEY_FILTER.sub("", sanitized)


def ensure_existing_pdf(pdf_path: str | Path) -> Path:
    path = Path(pdf_path).expanduser().resolve()
    if not path.exists():
        raise InvalidInputError(f"pdf path does not exist: {path}")
    if not path.is_file():
        raise InvalidInputError(f"pdf path is not a file: {path}")
    if path.suffix.lower() != ".pdf":
        raise InvalidInputError(f"file must use .pdf extension: {path}")
    return path


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_raw_copy_name(original_name: str, sha256_hex: str) -> str:
    stem = sanitize_title(Path(original_name).stem, max_length=80)
    return f"{sha256_hex[:8]}_{stem}.pdf"


def build_processed_filename(
    effective_index: int,
    title: str,
    *,
    hash_suffix: str | None = None,
) -> str:
    base = f"{effective_index:02d}_{sanitize_title(title)}"
    if hash_suffix:
        base = f"{base}_{hash_suffix[:8]}"
    return f"{base}.pdf"

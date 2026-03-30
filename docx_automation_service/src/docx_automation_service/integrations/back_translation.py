"""Layer 1 – Structural Reorganization via Multi-Language Back-Translation.

Strategy: Chinese → German/Japanese → English → Chinese

German and Japanese have fundamentally different grammar structures from Chinese.
Running text through these pivot languages forces automatic restructuring of
complex sentences, typically reducing plagiarism detection rates by 30–50 %.

The DeepL API is used for translation.  If the API key is absent the layer
is skipped gracefully and the original text is returned unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

import httpx

from docx_automation_service.core.config import settings

logger = logging.getLogger(__name__)

TranslationLang = Literal["ZH", "DE", "JA", "EN-US"]

# Supported translation chains.
# Key  : settings.translation_chain value
# Value: ordered list of language codes (first = source, last = target)
TRANSLATION_CHAINS: dict[str, list[TranslationLang]] = {
    "zh-de-en-zh": ["ZH", "DE", "EN-US", "ZH"],
    "zh-ja-en-zh": ["ZH", "JA", "EN-US", "ZH"],
}
_DEFAULT_CHAIN = "zh-de-en-zh"


class BackTranslationService:
    """Multi-hop back-translation for structural reorganization.

    Implements the **first layer** of the three-layer anti-plagiarism engine.
    Calling :py:meth:`back_translate` on a Chinese paragraph runs it through
    two intermediate languages before returning it to Chinese.  The detour
    forces sentence boundaries to shift, conjunctions to change, and clause
    order to rearrange – all without altering the semantic content.
    """

    def __init__(self) -> None:
        self._api_key: str = settings.deepl_api_key
        self._base_url: str = settings.deepl_base_url.rstrip("/")
        chain_key = settings.translation_chain
        self._chain: list[TranslationLang] = TRANSLATION_CHAINS.get(
            chain_key, TRANSLATION_CHAINS[_DEFAULT_CHAIN]
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return *True* when a DeepL API key has been configured."""
        return bool(self._api_key)

    async def back_translate(self, text: str) -> str:
        """Apply the full translation chain and return restructured text.

        Falls back silently to *text* if the API key is missing or if any
        translation step fails.
        """
        if not self.is_available():
            logger.debug("deepl api key not configured; back-translation skipped")
            return text

        current = text
        async with httpx.AsyncClient() as client:
            for i in range(len(self._chain) - 1):
                source = self._chain[i]
                target = self._chain[i + 1]
                logger.debug(
                    "back-translation step %s/%s | %s→%s | len=%s",
                    i + 1,
                    len(self._chain) - 1,
                    source,
                    target,
                    len(current),
                )
                try:
                    current = await self._translate(client, current, source, target)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "back-translation step %s→%s raised unexpectedly; "
                        "falling back to original text | error=%s",
                        source,
                        target,
                        exc,
                    )
                    return text

        logger.info(
            "back-translation complete | chain=%s | original_len=%s | result_len=%s",
            "→".join(self._chain),
            len(text),
            len(current),
        )
        return current

    async def back_translate_batch(self, texts: list[str]) -> list[str]:
        """Apply back-translation to multiple texts concurrently.

        Failed items fall back to their original text without raising.
        """
        if not self.is_available():
            return texts

        results = await asyncio.gather(
            *[self.back_translate(t) for t in texts],
            return_exceptions=True,
        )

        final: list[str] = []
        for original, result in zip(texts, results):
            if isinstance(result, Exception):
                logger.warning(
                    "back-translation chunk failed; falling back to original | error=%s",
                    result,
                )
                final.append(original)
            else:
                final.append(result)  # type: ignore[arg-type]
        return final

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _translate(
        self,
        client: httpx.AsyncClient,
        text: str,
        source_lang: TranslationLang,
        target_lang: TranslationLang,
    ) -> str:
        """Single DeepL translation call with graceful error handling."""
        headers = {
            "Authorization": f"DeepL-Auth-Key {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "text": [text],
            "source_lang": source_lang,
            "target_lang": target_lang,
        }
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=30.0)

        try:
            resp = await client.post(
                f"{self._base_url}/translate",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            translations = data.get("translations") or []
            if translations:
                return translations[0].get("text", text)
            return text
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "deepl http error | source=%s | target=%s | status=%s",
                source_lang,
                target_lang,
                exc.response.status_code,
            )
            return text
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "deepl error | source=%s | target=%s | error=%s",
                source_lang,
                target_lang,
                exc,
            )
            return text

"""Layer 1 – Structural Reorganization via Multi-Language Back-Translation.

Strategy: Chinese → German/Japanese → English → Chinese

German and Japanese have fundamentally different grammar structures from Chinese.
Running text through these pivot languages forces automatic restructuring of
complex sentences, typically reducing plagiarism detection rates by 30–50 %.

The Azure Translator API is used for translation.  If the API key is absent the layer
is skipped gracefully and the original text is returned unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Literal

import httpx

from docx_automation_service.core.config import settings

logger = logging.getLogger(__name__)

TranslationLang = Literal["zh-Hans", "zh-Hant", "de", "ja", "en"]

# Supported translation chains.
# Key  : settings.translation_chain value
# Value: ordered list of language codes (first = source, last = target)
TRANSLATION_CHAINS: dict[str, list[TranslationLang]] = {
    "zh-de-en-zh": ["zh-Hans", "de", "en", "zh-Hans"],
    "zh-ja-en-zh": ["zh-Hans", "ja", "en", "zh-Hans"],
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
        self._api_key: str = settings.azure_translator_key
        self._base_url: str = settings.azure_translator_endpoint.rstrip("/")
        self._region: str = settings.azure_translator_region
        chain_key = settings.translation_chain
        configured_chain = TRANSLATION_CHAINS.get(chain_key, TRANSLATION_CHAINS[_DEFAULT_CHAIN])
        source_lang = settings.translation_source_lang
        self._chain: list[TranslationLang] = configured_chain.copy()
        self._chain[0] = source_lang
        self._chain[-1] = source_lang

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def config_status(self) -> tuple[bool, str]:
        """Return (available, reason) for operational diagnostics."""
        if not self._api_key:
            return False, "azure_translator_key_missing"

        if not self._base_url:
            return False, "azure_translator_endpoint_missing"

        if settings.azure_translator_require_region and not self._region:
            return False, "azure_translator_region_missing"

        return True, "ok"

    def is_available(self) -> bool:
        """Return *True* when Azure Translator credentials are configured."""
        available, _ = self.config_status()
        return available

    def translation_chain(self) -> list[str]:
        """Return the effective translation chain for health/reporting."""
        return list(self._chain)

    async def back_translate(self, text: str) -> str:
        """Apply the full translation chain and return restructured text.

        Falls back silently to *text* if the API key is missing or if any
        translation step fails.
        """
        if not self.is_available():
            logger.debug("azure translator not configured; back-translation skipped")
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
        """Single Azure Translator call with graceful error handling."""
        headers = {
            "Ocp-Apim-Subscription-Key": self._api_key,
            "Content-Type": "application/json",
            "X-ClientTraceId": str(uuid.uuid4()),
        }
        if self._region:
            headers["Ocp-Apim-Subscription-Region"] = self._region

        payload: list[dict[str, str]] = [{"text": text}]
        params = {
            "api-version": "3.0",
            "from": source_lang,
            "to": target_lang,
        }
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=30.0)

        try:
            resp = await client.post(
                f"{self._base_url}/translate",
                headers=headers,
                json=payload,
                params=params,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list) or not data:
                return text
            translations = data[0].get("translations") or []
            if translations:
                return translations[0].get("text", text)
            return text
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "azure translator http error | source=%s | target=%s | status=%s",
                source_lang,
                target_lang,
                exc.response.status_code,
            )
            return text
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "azure translator error | source=%s | target=%s | error=%s",
                source_lang,
                target_lang,
                exc,
            )
            return text

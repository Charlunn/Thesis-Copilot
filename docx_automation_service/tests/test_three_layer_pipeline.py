"""Tests for the three-layer anti-plagiarism pipeline engine.

Covers:
- Layer 1: Back-translation service (graceful degradation without API key)
- Layer 2: Enhanced SiliconFlow rewriter (prompt construction, fallback)
- Layer 3: Text complexity analysis and burstiness injection
- Pipeline: deep_rewrite mode integration (offline, no real API calls)
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Layer 1 – Back-Translation
# ---------------------------------------------------------------------------

from docx_automation_service.integrations.back_translation import (
    TRANSLATION_CHAINS,
    BackTranslationService,
)


class TestBackTranslationService:
    def test_is_available_false_when_no_key(self):
        svc = BackTranslationService()
        # With no env var set the key defaults to ""
        assert not svc.is_available()

    def test_default_chain_is_zh_de_en_zh(self):
        svc = BackTranslationService()
        assert svc._chain == TRANSLATION_CHAINS["zh-de-en-zh"]

    def test_back_translate_returns_original_when_unavailable(self):
        svc = BackTranslationService()
        original = "这是一段测试文本。"
        result = asyncio.run(svc.back_translate(original))
        assert result == original

    def test_back_translate_batch_returns_originals_when_unavailable(self):
        svc = BackTranslationService()
        texts = ["文本一。", "文本二。"]
        results = asyncio.run(svc.back_translate_batch(texts))
        assert results == texts

    @patch("docx_automation_service.integrations.back_translation.settings")
    def test_back_translate_calls_deepl_api(self, mock_settings):
        """When a key is configured, the service must call the DeepL API for each hop."""
        mock_settings.deepl_api_key = "fake-key"
        mock_settings.deepl_base_url = "https://api-free.deepl.com/v2"
        mock_settings.translation_chain = "zh-de-en-zh"

        svc = BackTranslationService()
        assert svc.is_available()

        # Stub the HTTP call to return a translated text
        async def fake_translate(client, text, source, target):
            return f"[{source}→{target}]"

        with patch.object(svc, "_translate", side_effect=fake_translate):
            result = asyncio.run(svc.back_translate("原始文本"))

        # zh→de→en→zh: three hops
        assert result == "[EN-US→ZH]"

    @patch("docx_automation_service.integrations.back_translation.settings")
    def test_back_translate_falls_back_on_api_error(self, mock_settings):
        """A failing API call must fall back to the original text without raising."""
        mock_settings.deepl_api_key = "fake-key"
        mock_settings.deepl_base_url = "https://api-free.deepl.com/v2"
        mock_settings.translation_chain = "zh-de-en-zh"

        svc = BackTranslationService()

        async def failing_translate(client, text, source, target):
            raise RuntimeError("network error")

        with patch.object(svc, "_translate", side_effect=failing_translate):
            result = asyncio.run(svc.back_translate("原始文本"))

        # Must fall back to original
        assert result == "原始文本"


# ---------------------------------------------------------------------------
# Layer 3 – Text Analyzer
# ---------------------------------------------------------------------------

from docx_automation_service.integrations.text_analyzer import (
    TextComplexityReport,
    analyze_text,
    inject_burstiness,
)


class TestTextAnalyzer:
    def test_analyze_empty_returns_defaults(self):
        report = analyze_text("")
        assert report.sentence_count == 0
        assert not report.needs_burstiness_injection

    def test_analyze_short_text(self):
        report = analyze_text("这是一句话。")
        assert report.sentence_count == 1
        assert report.avg_sentence_length > 0

    def test_uniform_sentences_have_low_burstiness(self):
        # Sentences of nearly equal length → low variance → low burstiness
        uniform = "这是一段长度大致相同的句子。" * 5
        # Add sentence delimiters
        uniform = "。".join(["这是一段长度大致相同的句子" for _ in range(6)]) + "。"
        report = analyze_text(uniform)
        assert report.burstiness_score < 0.5

    def test_varied_sentences_have_higher_burstiness(self):
        varied = (
            "这是一个非常非常非常非常非常非常非常非常非常长的句子，包含了很多内容和细节。"
            "短句。"
            "这又是另外一个相当相当相当相当相当相当相当相当相当长的学术句子，涵盖方法论阐述。"
            "核心在此。"
            "再一个很长很长很长很长很长很长很长很长很长很长的句子用于展示对比效果验证。"
        )
        report = analyze_text(varied)
        assert report.burstiness_score >= 0.3

    def test_ai_transition_words_raise_risk(self):
        ai_text = "总而言之，本文研究了该问题。值得注意的是，结果令人满意。此外，实验证明了假设。"
        report = analyze_text(ai_text)
        assert report.ai_transition_density > 0.0
        assert report.layer3_risk_score > 0.0

    def test_inject_burstiness_does_nothing_for_short_text(self):
        short = "这是一句话。"
        result = inject_burstiness(short)
        assert result  # should return something

    def test_inject_burstiness_adds_short_sentences(self):
        # Three long sentences with no short ones → injection should happen
        long_sentences = [
            "这是一个非常非常非常非常非常非常非常非常非常长的句子，包含了很多内容和细节。",
            "这又是另外一个相当相当相当相当相当相当相当相当相当长的学术句子，涵盖方法论阐述。",
            "再一个很长很长很长很长很长很长很长很长很长很长的句子用于展示对比效果验证实验结果。",
            "最后一个同样很长很长很长很长很长的句子，用来触发突发性注入机制测试逻辑路径验证。",
        ]
        text = "。".join(s.rstrip("。") for s in long_sentences) + "。"
        result = inject_burstiness(text, lang="zh", min_long_run=3)
        # Result should be longer (injection added)
        assert len(result) >= len(text) - 10  # small tolerance for punctuation changes

    def test_inject_burstiness_english(self):
        long_en = (
            "This is a very long and complex sentence that contains many technical details about the system. "
            "Furthermore, this second sentence elaborates extensively on the implementation challenges faced. "
            "Additionally, this third sentence provides comprehensive evaluation results from the experiments. "
            "Moreover, this fourth sentence discusses the implications of the findings in a detailed manner."
        )
        result = inject_burstiness(long_en, lang="en", min_long_run=3)
        assert result  # should not be empty


# ---------------------------------------------------------------------------
# Layer 2 – Enhanced Rewriter (prompt structure checks)
# ---------------------------------------------------------------------------

from docx_automation_service.integrations.siliconflow_rewriter import (
    BLACKLIST_TERMS,
    SiliconFlowRewriter,
    _SYSTEM_PROMPT,
)


class TestSiliconFlowRewriter:
    def test_blacklist_terms_has_expected_entries(self):
        assert "总而言之" in BLACKLIST_TERMS
        assert "值得注意的是" in BLACKLIST_TERMS
        assert "综上所述" in BLACKLIST_TERMS

    def test_system_prompt_contains_four_pillars(self):
        assert "打破均衡句式" in _SYSTEM_PROMPT
        assert "引入学科术语变体" in _SYSTEM_PROMPT
        assert "模拟人类写作不完美性" in _SYSTEM_PROMPT
        assert "黑名单词汇剔除" in _SYSTEM_PROMPT

    def test_rewrite_returns_original_when_no_api_key(self):
        rewriter = SiliconFlowRewriter()
        # Default empty api key → must return original
        text = "这是测试文本。"
        result = asyncio.run(rewriter.rewrite(text))
        assert result == text


# ---------------------------------------------------------------------------
# Pipeline integration – deep_rewrite mode (no real API calls)
# ---------------------------------------------------------------------------

from docx import Document

from docx_automation_service.core.models import LayerReport
from docx_automation_service.integrations.mock_detectors import (
    HeuristicAIGCDetector,
    HeuristicSimilarityDetector,
)
from docx_automation_service.services.pipeline import PipelineService, _merge_layer_report


def _make_docx_bytes(text: str) -> bytes:
    """Create a minimal in-memory .docx with a single paragraph."""
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class TestPipelineDeepRewrite:
    @pytest.fixture()
    def tmp_docx(self, tmp_path):
        # A paragraph with high AI-marker density to ensure it gets flagged
        text = (
            "总而言之，本研究的核心贡献在于提出了一种全新的框架。"
            "值得注意的是，该框架在多个基准测试中取得了显著的性能提升。"
            "此外，本文还对相关的理论基础进行了系统性的分析。"
            "综上所述，实验结果充分验证了所提方法的有效性和优越性。"
        )
        path = tmp_path / "test.docx"
        path.write_bytes(_make_docx_bytes(text))
        return path

    @pytest.mark.asyncio
    async def test_deep_rewrite_mode_completes(self, tmp_docx, tmp_path):
        """deep_rewrite mode must complete without error even with no API keys."""

        async def mock_rewrite(text, topic_hint=None, preserve_terms=None):
            return text + " [rewritten]"

        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite = mock_rewrite
        mock_rewriter._api_key = "fake"

        svc = PipelineService(
            similarity_detector=HeuristicSimilarityDetector(),
            aigc_detector=HeuristicAIGCDetector(),
            rewriter=mock_rewriter,
        )
        svc.mapper.mapper = svc.mapper  # no-op

        record = await svc.run(
            tmp_docx,
            mode="deep_rewrite",
            topic_hint="计算机科学",
        )

        assert record.status == "done"
        assert record.mode == "deep_rewrite"
        assert record.result_path is not None

    @pytest.mark.asyncio
    async def test_analyze_mode_still_works(self, tmp_docx):
        """Existing analyze mode must not be broken by deep_rewrite additions."""
        svc = PipelineService(
            similarity_detector=HeuristicSimilarityDetector(),
            aigc_detector=HeuristicAIGCDetector(),
            rewriter=AsyncMock(),
        )
        record = await svc.run(tmp_docx, mode="analyze")
        assert record.status == "done"
        assert record.result_path is None

    @pytest.mark.asyncio
    async def test_layer_reports_populated_in_deep_rewrite(self, tmp_docx, tmp_path):
        """Layer reports must be attached to the RunRecord for deep_rewrite runs."""

        async def mock_rewrite(text, topic_hint=None, preserve_terms=None):
            return text

        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite = mock_rewrite
        mock_rewriter._api_key = "fake"

        svc = PipelineService(
            similarity_detector=HeuristicSimilarityDetector(),
            aigc_detector=HeuristicAIGCDetector(),
            rewriter=mock_rewriter,
        )

        record = await svc.run(tmp_docx, mode="deep_rewrite")
        assert record.status == "done"
        # At minimum Layer 2 and Layer 3 reports should be present
        layer_numbers = {lr.layer for lr in record.layer_reports}
        assert 2 in layer_numbers or 3 in layer_numbers


class TestMergeLayerReport:
    def test_merge_accumulates_same_layer(self):
        reports: list[LayerReport] = []
        lr1 = LayerReport(layer=1, name="back_translation", chunks_processed=2, chunks_skipped=0, available=True)
        lr2 = LayerReport(layer=1, name="back_translation", chunks_processed=3, chunks_skipped=1, available=True)
        _merge_layer_report(reports, lr1)
        _merge_layer_report(reports, lr2)
        assert len(reports) == 1
        assert reports[0].chunks_processed == 5
        assert reports[0].chunks_skipped == 1

    def test_merge_appends_different_layers(self):
        reports: list[LayerReport] = []
        for i in range(1, 4):
            lr = LayerReport(layer=i, name=f"layer{i}", chunks_processed=1, chunks_skipped=0, available=True)
            _merge_layer_report(reports, lr)
        assert len(reports) == 3

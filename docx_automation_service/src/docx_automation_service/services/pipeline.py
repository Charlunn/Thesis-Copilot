from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from docx_automation_service.core.config import settings
from docx_automation_service.core.models import ChunkRisk, LayerReport, RunRecord
from docx_automation_service.integrations.back_translation import BackTranslationService
from docx_automation_service.integrations.base import AIGCDetector, Rewriter, SimilarityDetector
from docx_automation_service.integrations.text_analyzer import analyze_text, inject_burstiness
from docx_automation_service.services.docx_mapper import DocxMapper

logger = logging.getLogger(__name__)


class PipelineService:
    def __init__(
        self,
        similarity_detector: SimilarityDetector,
        aigc_detector: AIGCDetector,
        rewriter: Rewriter,
        back_translator: BackTranslationService | None = None,
    ) -> None:
        self.similarity_detector = similarity_detector
        self.aigc_detector = aigc_detector
        self.rewriter = rewriter
        self.back_translator = back_translator or BackTranslationService()
        self.mapper = DocxMapper()
        self.records: dict[str, RunRecord] = {}

        settings.workdir.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        file_path: Path,
        mode: str,
        topic_hint: str | None = None,
        preserve_terms: list[str] | None = None,
    ) -> RunRecord:
        run_id = str(uuid.uuid4())
        run_dir = settings.workdir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        report_path = run_dir / "report.json"
        out_path = run_dir / "rewritten.docx"

        record = RunRecord(
            run_id=run_id,
            mode=mode,  # type: ignore[arg-type]
            status="running",
            report_path=report_path,
            result_path=out_path if mode in {"rewrite", "deep_rewrite"} else None,
        )
        self.records[run_id] = record

        try:
            logger.info("pipeline started | run_id=%s | mode=%s", run_id, mode)
            doc, chunks = self.mapper.extract_chunks(file_path)
            risks: list[ChunkRisk] = []
            rewrite_failures: list[dict[str, str]] = []
            layer_reports: list[LayerReport] = []

            logger.info("chunk extraction done | run_id=%s | chunk_total=%s", run_id, len(chunks))

            for chunk in chunks:
                sim = self.similarity_detector.score(chunk.text)
                aigc = self.aigc_detector.score(chunk.text)
                flagged = sim > settings.similarity_threshold or aigc > settings.aigc_threshold

                risks.append(
                    ChunkRisk(
                        chunk_id=chunk.chunk_id,
                        similarity_score=sim,
                        aigc_score=aigc,
                        flagged=flagged,
                    )
                )

                if mode == "rewrite" and flagged:
                    try:
                        rewritten = await self.rewriter.rewrite(
                            chunk.text,
                            topic_hint=topic_hint,
                            preserve_terms=preserve_terms,
                        )
                        self.mapper.apply_text(doc, chunk, rewritten)
                        logger.debug(
                            "chunk rewrite done | run_id=%s | chunk_id=%s | text_len=%s→%s",
                            run_id,
                            chunk.chunk_id,
                            len(chunk.text),
                            len(rewritten),
                        )
                    except Exception as exc:  # noqa: BLE001
                        rewrite_failures.append({"chunk_id": chunk.chunk_id, "error": str(exc)})
                        logger.warning(
                            "chunk rewrite failed; use original | run_id=%s | chunk_id=%s | error=%s",
                            run_id,
                            chunk.chunk_id,
                            exc,
                        )

                elif mode == "deep_rewrite" and flagged:
                    current_text, chunk_layer_reports = await self._deep_rewrite_chunk(
                        chunk.text,
                        chunk_id=chunk.chunk_id,
                        run_id=run_id,
                        topic_hint=topic_hint,
                        preserve_terms=preserve_terms,
                        rewrite_failures=rewrite_failures,
                    )
                    self.mapper.apply_text(doc, chunk, current_text)
                    for lr in chunk_layer_reports:
                        _merge_layer_report(layer_reports, lr)

                    # Attach per-chunk Layer 3 metrics to risk entry
                    risk_entry = next((r for r in risks if r.chunk_id == chunk.chunk_id), None)
                    if risk_entry is not None:
                        analysis = analyze_text(current_text)
                        risk_entry.burstiness_score = analysis.burstiness_score
                        risk_entry.layer3_risk_score = analysis.layer3_risk_score

            flagged_total = sum(1 for r in risks if r.flagged)
            logger.info(
                "risk analysis done | run_id=%s | flagged_total=%s | chunk_total=%s",
                run_id,
                flagged_total,
                len(chunks),
            )

            report = {
                "run_id": run_id,
                "mode": mode,
                "thresholds": {
                    "similarity_threshold": settings.similarity_threshold,
                    "aigc_threshold": settings.aigc_threshold,
                },
                "chunk_total": len(chunks),
                "flagged_total": flagged_total,
                "rewrite_failed_total": len(rewrite_failures),
                "rewrite_failures": rewrite_failures,
                "chunks": [r.model_dump() for r in risks],
            }
            if mode == "deep_rewrite":
                report["layer_reports"] = [lr.model_dump() for lr in layer_reports]

            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if mode in {"rewrite", "deep_rewrite"}:
                doc.save(str(out_path))
                logger.info("rewritten doc saved | run_id=%s | path=%s", run_id, out_path)

            record.status = "done"
            record.layer_reports = layer_reports
            self.records[run_id] = record
            logger.info("pipeline done | run_id=%s", run_id)
            return record
        except Exception as exc:  # noqa: BLE001
            record.status = "failed"
            record.error = str(exc)
            self.records[run_id] = record
            logger.exception("pipeline failed | run_id=%s | error=%s", run_id, exc)
            raise

    # ------------------------------------------------------------------
    # Deep-rewrite: three-layer chain for a single chunk
    # ------------------------------------------------------------------

    async def _deep_rewrite_chunk(
        self,
        text: str,
        *,
        chunk_id: str,
        run_id: str,
        topic_hint: str | None,
        preserve_terms: list[str] | None,
        rewrite_failures: list[dict[str, str]],
    ) -> tuple[str, list[LayerReport]]:
        """Run all three layers on one chunk.

        Returns the processed text and per-layer :class:`LayerReport` items.
        Failures are logged and appended to *rewrite_failures*; the layer falls
        back to its input text so downstream layers still run.
        """
        layer_reports: list[LayerReport] = []
        current = text

        # ---- Layer 1: Back-Translation --------------------------------
        layer1_available = self.back_translator.is_available()
        layer1_processed = 0
        if layer1_available:
            try:
                current = await self.back_translator.back_translate(current)
                layer1_processed = 1
                logger.debug(
                    "L1 back-translation done | run_id=%s | chunk_id=%s | len=%s→%s",
                    run_id, chunk_id, len(text), len(current),
                )
            except Exception as exc:  # noqa: BLE001
                rewrite_failures.append({"chunk_id": chunk_id, "error": f"L1: {exc}"})
                logger.warning("L1 back-translation failed | chunk_id=%s | error=%s", chunk_id, exc)
        else:
            logger.debug("L1 back-translation unavailable (no DeepL key) | chunk_id=%s", chunk_id)

        layer_reports.append(LayerReport(
            layer=1,
            name="back_translation",
            chunks_processed=layer1_processed,
            chunks_skipped=1 - layer1_processed,
            available=layer1_available,
        ))

        # ---- Layer 2: Semantic Restructuring --------------------------
        layer2_available = bool(getattr(self.rewriter, "_api_key", True))
        layer2_processed = 0
        try:
            rewritten = await self.rewriter.rewrite(
                current,
                topic_hint=topic_hint,
                preserve_terms=preserve_terms,
            )
            if rewritten and rewritten.strip():
                current = rewritten
                layer2_processed = 1
            logger.debug(
                "L2 semantic rewrite done | run_id=%s | chunk_id=%s | len=%s→%s",
                run_id, chunk_id, len(text), len(current),
            )
        except Exception as exc:  # noqa: BLE001
            rewrite_failures.append({"chunk_id": chunk_id, "error": f"L2: {exc}"})
            logger.warning("L2 semantic rewrite failed | chunk_id=%s | error=%s", chunk_id, exc)

        layer_reports.append(LayerReport(
            layer=2,
            name="semantic_restructure",
            chunks_processed=layer2_processed,
            chunks_skipped=1 - layer2_processed,
            available=layer2_available,
        ))

        # ---- Layer 3: Burstiness Injection ----------------------------
        analysis = analyze_text(current)
        layer3_processed = 0
        if analysis.needs_burstiness_injection:
            current = inject_burstiness(
                current,
                lang=settings.burstiness_lang,
                min_long_run=settings.burstiness_min_long_run,
            )
            layer3_processed = 1
            logger.debug(
                "L3 burstiness injection done | chunk_id=%s | burstiness_before=%.3f",
                chunk_id, analysis.burstiness_score,
            )
        else:
            logger.debug(
                "L3 burstiness injection skipped (score=%.3f ≥ threshold=%.3f) | chunk_id=%s",
                analysis.burstiness_score,
                settings.burstiness_injection_threshold,
                chunk_id,
            )

        layer_reports.append(LayerReport(
            layer=3,
            name="burstiness_injection",
            chunks_processed=layer3_processed,
            chunks_skipped=1 - layer3_processed,
            available=True,
        ))

        return current, layer_reports

    def get_record(self, run_id: str) -> RunRecord | None:
        return self.records.get(run_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_layer_report(existing: list[LayerReport], new: LayerReport) -> None:
    """Accumulate chunk-level layer stats into a run-level list."""
    for lr in existing:
        if lr.layer == new.layer:
            lr.chunks_processed += new.chunks_processed
            lr.chunks_skipped += new.chunks_skipped
            return
    existing.append(LayerReport(
        layer=new.layer,
        name=new.name,
        chunks_processed=new.chunks_processed,
        chunks_skipped=new.chunks_skipped,
        available=new.available,
    ))

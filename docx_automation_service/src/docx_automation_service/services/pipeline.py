from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from docx_automation_service.core.config import settings
from docx_automation_service.core.models import ChunkRisk, LayerReport, RunRecord
from docx_automation_service.integrations.back_translation import BackTranslationService
from docx_automation_service.integrations.base import AIGCDetector, Rewriter, SimilarityDetector
from docx_automation_service.integrations.text_analyzer import analyze_text, inject_burstiness
from docx_automation_service.services.docx_mapper import DocxMapper
from docx_automation_service.services.text_guard import sanitize_model_output, split_for_rewrite

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
        self.tasks: dict[str, asyncio.Task] = {}

        settings.workdir.mkdir(parents=True, exist_ok=True)

    def create_run_record(self, mode: str) -> RunRecord:
        run_id = str(uuid.uuid4())
        run_dir = settings.workdir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        record = RunRecord(
            run_id=run_id,
            mode=mode,  # type: ignore[arg-type]
            status="queued",
            report_path=run_dir / "report.json",
            result_path=(run_dir / "rewritten.docx") if mode in {"rewrite", "deep_rewrite"} else None,
            current_stage="queued",
            progress_percent=0.0,
            updated_at=datetime.now(timezone.utc),
        )
        self.records[run_id] = record
        self._persist_record(record)
        return record

    def update_run_options(self, run_id: str, *, model_name: str | None, enable_reasoning: bool) -> None:
        self._update_record(
            run_id,
            llm_model=(model_name or "").strip() or None,
            reasoning_enabled=enable_reasoning,
        )

    def start_run_in_background(
        self,
        *,
        run_id: str,
        file_path: Path,
        mode: str,
        topic_hint: str | None,
        preserve_terms: list[str] | None,
        model_name: str | None = None,
        enable_reasoning: bool = True,
    ) -> None:
        task = asyncio.create_task(
            self.run_existing(
                run_id=run_id,
                file_path=file_path,
                mode=mode,
                topic_hint=topic_hint,
                preserve_terms=preserve_terms,
                model_name=model_name,
                enable_reasoning=enable_reasoning,
            )
        )
        self.tasks[run_id] = task

        def _cleanup(_: asyncio.Task) -> None:
            self.tasks.pop(run_id, None)

        task.add_done_callback(_cleanup)

    async def run(
        self,
        file_path: Path,
        mode: str,
        topic_hint: str | None = None,
        preserve_terms: list[str] | None = None,
        model_name: str | None = None,
        enable_reasoning: bool = True,
    ) -> RunRecord:
        record = self.create_run_record(mode)
        self.update_run_options(record.run_id, model_name=model_name, enable_reasoning=enable_reasoning)
        await self.run_existing(
            run_id=record.run_id,
            file_path=file_path,
            mode=mode,
            topic_hint=topic_hint,
            preserve_terms=preserve_terms,
            model_name=model_name,
            enable_reasoning=enable_reasoning,
        )
        return self.records[record.run_id]

    async def run_existing(
        self,
        *,
        run_id: str,
        file_path: Path,
        mode: str,
        topic_hint: str | None = None,
        preserve_terms: list[str] | None = None,
        model_name: str | None = None,
        enable_reasoning: bool = True,
    ) -> RunRecord:
        record = self.records.get(run_id)
        if record is None:
            record = self.create_run_record(mode)
            run_id = record.run_id

        preserve_terms = preserve_terms or []
        self.update_run_options(run_id, model_name=model_name, enable_reasoning=enable_reasoning)

        try:
            self._update_record(
                run_id,
                status="running",
                current_stage="extracting",
                progress_percent=2.0,
                message="正在解析文档...",
                started_at=datetime.now(timezone.utc),
            )
            logger.info("pipeline started | run_id=%s | mode=%s", run_id, mode)
            doc, chunks = self.mapper.extract_chunks(file_path)
            risks: list[ChunkRisk] = []
            rewrite_failures: list[dict[str, str]] = []
            layer_reports: list[LayerReport] = []
            total_chunks = len(chunks)
            self._update_record(
                run_id,
                total_chunks=total_chunks,
                current_chunk=0,
                current_stage="detecting",
                progress_percent=5.0,
                message="正在检测文本风险...",
            )

            logger.info("chunk extraction done | run_id=%s | chunk_total=%s", run_id, len(chunks))

            for idx, chunk in enumerate(chunks, start=1):
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
                        if settings.rewrite_skip_heading_chunks and chunk.ref.is_heading:
                            rewritten = chunk.text
                        else:
                            rewritten = await self._rewrite_with_split(
                                chunk.text,
                                topic_hint=topic_hint,
                                preserve_terms=preserve_terms,
                                source_is_heading=chunk.ref.is_heading,
                                model_name=model_name,
                                enable_reasoning=enable_reasoning,
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

                elif mode == "deep_rewrite" and (flagged or settings.deep_rewrite_process_all_chunks):
                    current_text, chunk_layer_reports = await self._deep_rewrite_chunk(
                        chunk.text,
                        chunk=chunk,
                        chunk_id=chunk.chunk_id,
                        run_id=run_id,
                        topic_hint=topic_hint,
                        preserve_terms=preserve_terms,
                        model_name=model_name,
                        enable_reasoning=enable_reasoning,
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

                self._update_progress_by_chunk(
                    run_id,
                    mode=mode,
                    current_chunk=idx,
                    total_chunks=total_chunks,
                )

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
                "chunks": [r.model_dump(exclude_none=True) for r in risks],
            }
            if mode == "deep_rewrite":
                report["layer_reports"] = [lr.model_dump() for lr in layer_reports]

            report_path = self._run_dir(run_id) / "report.json"
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

            self._update_record(
                run_id,
                current_stage="finalizing",
                progress_percent=96.0,
                message="正在保存结果...",
            )
            if mode in {"rewrite", "deep_rewrite"}:
                out_path = self._run_dir(run_id) / "rewritten.docx"
                doc.save(str(out_path))
                logger.info("rewritten doc saved | run_id=%s | path=%s", run_id, out_path)

            self._update_record(
                run_id,
                status="done",
                current_stage="done",
                progress_percent=100.0,
                message="任务完成",
                completed_at=datetime.now(timezone.utc),
                layer_reports=layer_reports,
                error=None,
                eta_seconds=0,
            )
            logger.info("pipeline done | run_id=%s", run_id)
            return self.records[run_id]
        except asyncio.CancelledError:
            self._update_record(
                run_id,
                status="canceled",
                current_stage="canceled",
                message="任务已取消",
                completed_at=datetime.now(timezone.utc),
                eta_seconds=0,
            )
            logger.info("pipeline canceled | run_id=%s", run_id)
            return self.records[run_id]
        except Exception as exc:  # noqa: BLE001
            self._update_record(
                run_id,
                status="failed",
                current_stage="failed",
                message="任务失败",
                error=str(exc),
                completed_at=datetime.now(timezone.utc),
            )
            if settings.log_exception_stack:
                logger.exception("pipeline failed | run_id=%s | error=%s", run_id, exc)
            else:
                logger.error("pipeline failed | run_id=%s | error=%s", run_id, exc)
            raise

    # ------------------------------------------------------------------
    # Deep-rewrite: three-layer chain for a single chunk
    # ------------------------------------------------------------------

    async def _deep_rewrite_chunk(
        self,
        text: str,
        *,
        chunk,
        chunk_id: str,
        run_id: str,
        topic_hint: str | None,
        preserve_terms: list[str] | None,
        model_name: str | None,
        enable_reasoning: bool,
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
        layer1_available = self.back_translator.is_available() and not chunk.ref.is_heading
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
            logger.debug("L1 back-translation unavailable or skipped | chunk_id=%s", chunk_id)

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
            if settings.rewrite_skip_heading_chunks and chunk.ref.is_heading:
                rewritten = current
            else:
                rewritten = await self._rewrite_with_split(
                    current,
                    topic_hint=topic_hint,
                    preserve_terms=preserve_terms,
                    source_is_heading=chunk.ref.is_heading,
                    model_name=model_name,
                    enable_reasoning=enable_reasoning,
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
        record = self.records.get(run_id)
        if record:
            return record
        return self.load_record_from_disk(run_id)

    def list_records(self, limit: int = 50) -> list[RunRecord]:
        run_dirs = [p for p in settings.workdir.iterdir() if p.is_dir()]
        records: list[RunRecord] = []
        for run_dir in run_dirs:
            run_id = run_dir.name
            record = self.records.get(run_id) or self.load_record_from_disk(run_id)
            if record:
                records.append(record)

        records.sort(key=lambda x: x.updated_at or x.created_at, reverse=True)
        return records[:limit]

    def load_record_from_disk(self, run_id: str) -> RunRecord | None:
        run_json = self._record_path(run_id)
        if not run_json.exists():
            return None
        try:
            data = json.loads(run_json.read_text(encoding="utf-8"))
            record = RunRecord.model_validate(data)
            self.records[run_id] = record
            return record
        except Exception as exc:  # noqa: BLE001
            logger.warning("failed to load run record from disk | run_id=%s | error=%s", run_id, exc)
            return None

    async def _rewrite_with_split(
        self,
        text: str,
        *,
        topic_hint: str | None,
        preserve_terms: list[str],
        source_is_heading: bool,
        model_name: str | None,
        enable_reasoning: bool,
    ) -> str:
        chunks = split_for_rewrite(
            text,
            target_chars=settings.rewrite_chunk_target_chars,
            max_chars=settings.rewrite_chunk_max_chars,
        )
        rewritten_parts: list[str] = []
        for part in chunks:
            rewritten = await self._rewrite_once(
                part,
                topic_hint=topic_hint,
                preserve_terms=preserve_terms,
                model_name=model_name,
                enable_reasoning=enable_reasoning,
            )
            if settings.sanitize_model_output:
                rewritten = sanitize_model_output(
                    rewritten,
                    original_text=part,
                    source_is_heading=source_is_heading,
                )
            rewritten_parts.append(rewritten)

        return "".join(rewritten_parts).strip() or text

    async def _rewrite_once(
        self,
        text: str,
        *,
        topic_hint: str | None,
        preserve_terms: list[str],
        model_name: str | None,
        enable_reasoning: bool,
    ) -> str:
        try:
            return await self.rewriter.rewrite(
                text,
                topic_hint=topic_hint,
                preserve_terms=preserve_terms,
                model_name=model_name,
                enable_reasoning=enable_reasoning,
            )
        except TypeError:
            return await self.rewriter.rewrite(
                text,
                topic_hint=topic_hint,
                preserve_terms=preserve_terms,
            )

    def _run_dir(self, run_id: str) -> Path:
        run_dir = settings.workdir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _record_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "run.json"

    def _persist_record(self, record: RunRecord) -> None:
        payload = record.model_dump(mode="json")
        self._record_path(record.run_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _update_record(self, run_id: str, **changes) -> None:
        record = self.records.get(run_id)
        if record is None:
            return

        data = record.model_dump()
        data.update(changes)
        data["updated_at"] = datetime.now(timezone.utc)
        updated = RunRecord.model_validate(data)
        self.records[run_id] = updated
        self._persist_record(updated)

    def _update_progress_by_chunk(self, run_id: str, *, mode: str, current_chunk: int, total_chunks: int) -> None:
        if total_chunks <= 0:
            return

        ratio = current_chunk / total_chunks
        stage = "detecting" if mode == "analyze" else "rewriting"
        progress = 5.0 + ratio * 87.0
        eta = self._estimate_eta(run_id, current_chunk, total_chunks)
        self._update_record(
            run_id,
            current_chunk=current_chunk,
            total_chunks=total_chunks,
            current_stage=stage,
            progress_percent=min(95.0, progress),
            eta_seconds=eta,
            message=f"正在处理第 {current_chunk}/{total_chunks} 段",
        )

    def _estimate_eta(self, run_id: str, current_chunk: int, total_chunks: int) -> int | None:
        record = self.records.get(run_id)
        if record is None or record.started_at is None or current_chunk <= 0:
            return None

        elapsed = (datetime.now(timezone.utc) - record.started_at).total_seconds()
        avg = elapsed / max(1, current_chunk)
        remaining = max(0, total_chunks - current_chunk)
        return int(avg * remaining)

    def cancel_run(self, run_id: str) -> RunRecord | None:
        record = self.get_record(run_id)
        if record is None:
            return None

        if record.status in {"done", "failed", "canceled"}:
            return record

        task = self.tasks.get(run_id)
        if task and not task.done():
            task.cancel()

        self._update_record(
            run_id,
            status="canceled",
            current_stage="canceled",
            message="任务已取消",
            completed_at=datetime.now(timezone.utc),
            eta_seconds=0,
        )
        return self.records.get(run_id) or record


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

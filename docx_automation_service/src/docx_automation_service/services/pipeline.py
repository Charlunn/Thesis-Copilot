from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from docx_automation_service.core.config import settings
from docx_automation_service.core.models import ChunkRisk, RunRecord
from docx_automation_service.integrations.base import AIGCDetector, Rewriter, SimilarityDetector
from docx_automation_service.services.docx_mapper import DocxMapper

logger = logging.getLogger(__name__)


class PipelineService:
    def __init__(
        self,
        similarity_detector: SimilarityDetector,
        aigc_detector: AIGCDetector,
        rewriter: Rewriter,
    ) -> None:
        self.similarity_detector = similarity_detector
        self.aigc_detector = aigc_detector
        self.rewriter = rewriter
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
            mode=mode,
            status="running",
            report_path=report_path,
            result_path=out_path if mode == "rewrite" else None,
        )
        self.records[run_id] = record

        try:
            logger.info("pipeline started | run_id=%s | mode=%s", run_id, mode)
            doc, chunks = self.mapper.extract_chunks(file_path)
            risks: list[ChunkRisk] = []
            rewrite_failures: list[dict[str, str]] = []
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
                        # Degrade to original chunk and continue processing.
                        rewrite_failures.append({"chunk_id": chunk.chunk_id, "error": str(exc)})
                        logger.warning(
                            "chunk rewrite failed; use original | run_id=%s | chunk_id=%s | error=%s",
                            run_id,
                            chunk.chunk_id,
                            exc,
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
                "chunks": [r.model_dump() for r in risks],
            }

            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if mode == "rewrite":
                doc.save(str(out_path))
                logger.info("rewritten doc saved | run_id=%s | path=%s", run_id, out_path)

            record.status = "done"
            self.records[run_id] = record
            logger.info("pipeline done | run_id=%s", run_id)
            return record
        except Exception as exc:  # noqa: BLE001
            record.status = "failed"
            record.error = str(exc)
            self.records[run_id] = record
            logger.exception("pipeline failed | run_id=%s | error=%s", run_id, exc)
            raise

    def get_record(self, run_id: str) -> RunRecord | None:
        return self.records.get(run_id)

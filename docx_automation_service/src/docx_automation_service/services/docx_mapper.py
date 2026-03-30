from __future__ import annotations

from pathlib import Path

from docx import Document

from docx_automation_service.core.models import Chunk, ChunkRef


class DocxMapper:
    def extract_chunks(self, file_path: Path) -> tuple[Document, list[Chunk]]:
        doc = Document(str(file_path))
        chunks: list[Chunk] = []

        p_idx = 0
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                chunks.append(
                    Chunk(
                        chunk_id=f"p-{p_idx}",
                        text=text,
                        ref=ChunkRef(block_type="paragraph", paragraph_index=p_idx),
                    )
                )
            p_idx += 1

        for t_idx, table in enumerate(doc.tables):
            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row.cells):
                    text = "\n".join(p.text for p in cell.paragraphs).strip()
                    if not text:
                        continue
                    chunks.append(
                        Chunk(
                            chunk_id=f"t-{t_idx}-r-{r_idx}-c-{c_idx}",
                            text=text,
                            ref=ChunkRef(
                                block_type="table_cell",
                                table_index=t_idx,
                                row_index=r_idx,
                                cell_index=c_idx,
                            ),
                        )
                    )

        return doc, chunks

    def apply_text(self, doc: Document, chunk: Chunk, new_text: str) -> None:
        ref = chunk.ref
        text = new_text.strip()
        if not text:
            return

        if ref.block_type == "paragraph" and ref.paragraph_index is not None:
            para = doc.paragraphs[ref.paragraph_index]
            self._replace_in_paragraph(para, text)
            return

        if (
            ref.block_type == "table_cell"
            and ref.table_index is not None
            and ref.row_index is not None
            and ref.cell_index is not None
        ):
            cell = doc.tables[ref.table_index].rows[ref.row_index].cells[ref.cell_index]
            first_para = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
            self._replace_in_paragraph(first_para, text)
            for extra_para in cell.paragraphs[1:]:
                self._replace_in_paragraph(extra_para, "")

    @staticmethod
    def _replace_in_paragraph(para, text: str) -> None:
        if para.runs:
            para.runs[0].text = text
            for run in para.runs[1:]:
                run.text = ""
            return
        para.add_run(text)

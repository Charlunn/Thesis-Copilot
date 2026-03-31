from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from qnu_copilot.services.errors import ConflictError, NotFoundError
from qnu_copilot.services.workspace import WorkspaceManager


class PromptFactoryService:
    def __init__(self, workspace_manager: WorkspaceManager) -> None:
        self.workspace_manager = workspace_manager

    def render_reference_recommendation_prompt(self, project_id: str) -> tuple[str, Path]:
        state = self.workspace_manager.load_state(project_id)
        if not state.project.need_reference_recommendation:
            raise ConflictError(
                "reference recommendation prompt is only available for recommended-reference projects"
            )

        prompt_text = (
            "你是论文参考文献检索助手。请根据以下项目信息，输出严格 JSON，不要输出 Markdown 代码块。\n\n"
            f"论文题目：{state.project.title}\n"
            f"核心思想：{state.project.core_idea}\n"
            f"学科方向：{state.project.discipline or '未提供'}\n"
            f"关键词：{', '.join(state.project.keywords) if state.project.keywords else '未提供'}\n"
            f"最低参考文献数量：{state.references.minimum_required}\n\n"
            "请推荐与该选题高度相关的参考文献，结果必须满足：\n"
            "1. 中文论文至少 15 篇，英文论文至少 15 篇。\n"
            "2. 每篇都必须给出 title、language、download_url、bibtex。\n"
            "3. language 只能使用 zh 或 en。\n"
            "4. download_url 尽量提供可以实际访问的 PDF 或论文落地页链接。\n"
            "5. 不要解释，不要附加说明，只返回 JSON。\n\n"
            "补充约束：impact_note 要具体、克制，避免空泛套话。\n\n"
            "输出 JSON 结构必须为：\n"
            '{\n'
            '  "topic": "论文主题",\n'
            '  "papers": [\n'
            "    {\n"
            '      "title": "论文标题",\n'
            '      "language": "zh",\n'
            '      "year": 2024,\n'
            '      "venue": "期刊或会议",\n'
            '      "download_url": "https://...",\n'
            '      "impact_note": "推荐理由",\n'
            '      "bibtex": "@article{...}"\n'
            "    }\n"
            "  ]\n"
            "}\n"
        )
        snapshot = self.workspace_manager.write_prompt_snapshot(
            project_id,
            prompt_name="reference_recommendation_prompt",
            prompt_text=prompt_text,
        )
        return prompt_text, snapshot

    def render_outline_prompt(self, project_id: str) -> tuple[str, Path]:
        state = self.workspace_manager.load_state(project_id)
        if len(state.references.processed_items) < state.references.minimum_required:
            raise ConflictError("the minimum number of processed PDFs is required before rendering outline prompt")

        references = [
            {
                "effective_index": item.effective_index,
                "title": item.title,
                "language": item.language,
                "bibtex_key": item.bibtex_key,
            }
            for item in state.references.processed_items
        ]
        prompt_text = (
            "你是 NotebookLM 中的论文提纲生成助手。请基于用户已经上传到 NotebookLM 的 PDF，"
            "为当前论文生成严格 JSON，不要输出 Markdown 代码块。\n\n"
            f"{self._natural_style_constraints()}\n\n"
            f"论文题目：{state.project.title}\n"
            f"核心思想：{state.project.core_idea}\n"
            f"最低总字数：{state.project.minimum_total_words or '未设置'}\n"
            "已整理参考文献：\n"
            f"{json.dumps(references, ensure_ascii=False, indent=2)}\n\n"
            "要求：\n"
            "1. 提纲必须适合本科毕业论文写作。\n"
            "2. 根节点至少 3 个一级章节，且一级章节 level 必须为 1。\n"
            "3. 子节点 level 必须等于父节点 level + 1。\n"
            "4. id 使用层级编号样式，例如 1、1.1、1.1.1。\n"
            "5. 只输出 JSON，不要附加说明。\n\n"
            "输出 JSON 结构必须为：\n"
            '{\n'
            '  "title": "论文标题",\n'
            '  "outline": [\n'
            "    {\n"
            '      "id": "1",\n'
            '      "level": 1,\n'
            '      "title": "绪论",\n'
            '      "children": [\n'
            "        {\n"
            '          "id": "1.1",\n'
            '          "level": 2,\n'
            '          "title": "研究背景",\n'
            '          "children": []\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n"
        )
        snapshot = self.workspace_manager.write_prompt_snapshot(
            project_id,
            prompt_name="outline_prompt",
            prompt_text=prompt_text,
        )
        return prompt_text, snapshot

    def render_chunk_plan_prompt(self, project_id: str) -> tuple[str, Path]:
        state = self.workspace_manager.load_state(project_id)
        if not state.outline.confirmed_tree:
            raise ConflictError("confirmed outline is required before rendering chunk plan prompt")

        prompt_text = (
            "你是论文切块规划助手。请根据以下项目信息，输出严格 JSON，不要输出 Markdown 代码块。\n\n"
            f"{self._natural_style_constraints()}\n\n"
            f"论文题目：{state.project.title}\n"
            f"核心思想：{state.project.core_idea}\n"
            f"最低总字数：{state.project.minimum_total_words or '未设置'}\n\n"
            "最终确认版大纲：\n"
            f"{json.dumps(state.outline.confirmed_tree, ensure_ascii=False, indent=2)}\n\n"
            "请输出 JSON，结构必须为：\n"
            '{\n  "total_blocks": 8,\n  "blocks": [\n    {\n      "block_index": 1,\n      "title": "块标题",\n      "outline_node_ids": ["1", "1.1"],\n      "goal": "本块写作目标",\n      "minimum_words": 1200,\n      "citation_focus": ["主题A", "主题B"]\n    }\n  ]\n}\n\n'
            "要求：\n"
            "1. 覆盖所有 enabled=true 的大纲节点。\n"
            "2. block_index 从 1 连续递增。\n"
            "3. minimum_words 总和不少于最低总字数；如果未设置最低总字数，请按本科论文常规章节合理分配。\n"
            "4. 不要省略字段，不要解释。"
        )
        snapshot = self.workspace_manager.write_prompt_snapshot(
            project_id,
            prompt_name="chunk_plan_prompt",
            prompt_text=prompt_text,
        )
        return prompt_text, snapshot

    def render_block_generation_prompt(
        self,
        project_id: str,
        block_index: int,
    ) -> tuple[str, Path]:
        state = self.workspace_manager.load_state(project_id)
        if not state.chunk_plan.confirmed_plan:
            raise ConflictError("confirmed chunk plan is required before rendering block prompt")

        block_plan = self._get_block_plan(state.chunk_plan.confirmed_plan, block_index)
        references = [
            {
                "effective_index": item.effective_index,
                "title": item.title,
                "language": item.language,
            }
            for item in state.references.processed_items
        ]
        completed_blocks = [
            block.normalized_json
            for block in state.generation.blocks
            if block.normalized_json is not None and block.block_index < block_index
        ]

        prompt_text = (
            "你是 NotebookLM 中的学术正文生成助手。请基于已上传 PDF 来源，为当前论文块生成严格 JSON，不要输出 Markdown 代码块。\n\n"
            f"{self._natural_style_constraints()}\n\n"
            f"论文题目：{state.project.title}\n"
            f"核心思想：{state.project.core_idea}\n"
            f"当前块编号：{block_plan['block_index']}\n"
            f"当前块标题：{block_plan['title']}\n"
            f"当前块目标：{block_plan['goal']}\n"
            f"当前块最低字数：{block_plan['minimum_words']}\n"
            f"当前块覆盖节点：{json.dumps(block_plan['outline_node_ids'], ensure_ascii=False)}\n"
            f"重点引用主题：{json.dumps(block_plan['citation_focus'], ensure_ascii=False)}\n\n"
            "最终确认版大纲：\n"
            f"{json.dumps(state.outline.confirmed_tree, ensure_ascii=False, indent=2)}\n\n"
            "可用参考文献清单：\n"
            f"{json.dumps(references, ensure_ascii=False, indent=2)}\n\n"
            "前文压缩上下文：\n"
            f"{json.dumps(state.generation.latest_compressed_context or {}, ensure_ascii=False, indent=2)}\n\n"
            "已完成块（仅供避免重复，不要照抄）：\n"
            f"{json.dumps(completed_blocks, ensure_ascii=False, indent=2)}\n\n"
            "请输出 JSON，结构必须为：\n"
            '{\n  "block_index": 1,\n  "block_title": "块标题",\n  "content": [\n    {"type": "h1", "text": "第1章 绪论"},\n    {"type": "h2", "text": "1.1 研究背景"},\n    {"type": "p", "text": "正文内容【文献01】"}\n  ]\n}\n\n'
            "要求：\n"
            "1. 只允许 type 为 h1/h2/h3/p/list/table_placeholder。\n"
            "2. 引用必须使用【文献XX】占位符。\n"
            "3. 行文保持学术中文风格，不要输出说明文字。\n"
            "4. block_index 必须与当前块编号一致。"
        )
        snapshot = self.workspace_manager.write_prompt_snapshot(
            project_id,
            prompt_name=f"block_{block_index:02d}_generate_prompt",
            prompt_text=prompt_text,
        )
        return prompt_text, snapshot

    def render_compress_prompt(
        self,
        project_id: str,
        block_index: int,
    ) -> tuple[str, Path]:
        state = self.workspace_manager.load_state(project_id)
        if not state.chunk_plan.confirmed_plan:
            raise ConflictError("confirmed chunk plan is required before rendering compression prompt")
        block_state = self._get_generation_block(state.generation.blocks, block_index)
        if block_state.normalized_json is None:
            raise ConflictError("current block content must be imported before compression")
        if block_index >= state.generation.total_blocks:
            raise ConflictError("the final block does not need compressed context")

        imported_blocks = [
            block.normalized_json
            for block in state.generation.blocks
            if block.normalized_json is not None and block.block_index <= block_index
        ]
        remaining_blocks = [
            block
            for block in state.chunk_plan.confirmed_plan["blocks"]
            if block["block_index"] > block_index
        ]

        prompt_text = (
            "你是论文上下文压缩助手。请把当前已生成的论文块压缩为严格 JSON，不要输出 Markdown 代码块。\n\n"
            f"{self._natural_style_constraints()}\n\n"
            f"已完成块截止：第 {block_index} 块\n"
            "已完成块内容：\n"
            f"{json.dumps(imported_blocks, ensure_ascii=False, indent=2)}\n\n"
            "后续待写块规划：\n"
            f"{json.dumps(remaining_blocks, ensure_ascii=False, indent=2)}\n\n"
            "请输出 JSON，结构必须为：\n"
            '{\n  "covered_blocks": [1, 2],\n  "compressed_context": {\n    "narrative_summary": "前文总结",\n    "key_claims": ["论点A"],\n    "used_citations": ["文献01"],\n    "pending_topics": ["实验设计"],\n    "style_constraints": ["保持学术口吻"]\n  }\n}\n\n'
            "要求：\n"
            "1. covered_blocks 必须覆盖当前所有已完成块。\n"
            "2. narrative_summary 必须非空。\n"
            "3. 结果要足够供下一块生成继续沿用风格与逻辑。"
        )
        snapshot = self.workspace_manager.write_prompt_snapshot(
            project_id,
            prompt_name=f"block_{block_index:02d}_compress_prompt",
            prompt_text=prompt_text,
        )
        return prompt_text, snapshot

    def render_abstract_prompt(self, project_id: str) -> tuple[str, Path]:
        state = self.workspace_manager.load_state(project_id)
        if not state.chunk_plan.confirmed_plan:
            raise ConflictError("confirmed chunk plan is required before rendering abstract prompt")
        if not state.generation.blocks:
            raise ConflictError("generated blocks are required before rendering abstract prompt")
        if any(block.normalized_json is None for block in state.generation.blocks):
            raise ConflictError("all body blocks must be imported before rendering abstract prompt")

        compressed_body = self._build_final_body_context(state.generation.blocks)
        prompt_text = (
            "你是学术摘要生成助手。请先理解并压缩正文语义，再输出严格 JSON，不要输出 Markdown 代码块。\n\n"
            f"{self._natural_style_constraints()}\n\n"
            f"论文题目：{state.project.title}\n"
            f"核心思想：{state.project.core_idea}\n"
            "正文压缩上下文（由系统从完整正文生成）：\n"
            f"{json.dumps(compressed_body, ensure_ascii=False, indent=2)}\n\n"
            "请输出 JSON，结构必须为：\n"
            '{\n  "title": "摘要",\n  "content": ["摘要段落1", "摘要段落2"],\n  "keywords": ["关键词1", "关键词2", "关键词3"]\n}\n\n'
            "要求：\n"
            "1. 摘要应覆盖研究背景、方法、结果与结论，不得与正文机械重复。\n"
            "2. content 至少 2 段，每段 120-220 字，中文学术表达自然流畅。\n"
            "3. keywords 建议 3-5 个，避免空泛词汇。\n"
            "4. 只输出 JSON，不要附加解释。"
        )
        snapshot = self.workspace_manager.write_prompt_snapshot(
            project_id,
            prompt_name="abstract_prompt",
            prompt_text=prompt_text,
        )
        return prompt_text, snapshot

    def _get_block_plan(self, confirmed_plan: dict[str, Any], block_index: int) -> dict[str, Any]:
        for block in confirmed_plan["blocks"]:
            if block["block_index"] == block_index:
                return block
        raise NotFoundError(f"chunk plan block does not exist: {block_index}")

    def _get_generation_block(self, blocks: list[Any], block_index: int) -> Any:
        for block in blocks:
            if block.block_index == block_index:
                return block
        raise NotFoundError(f"generation block does not exist: {block_index}")

    def _natural_style_constraints(self) -> str:
        return (
            "写作风格约束：避免模板化句式与堆砌连接词；句长应有自然变化；"
            "优先使用具体论证与可核查表述；必要时用审慎措辞表达边界条件；"
            "保持学术严谨但不生硬。"
        )

    def _build_final_body_context(self, blocks: list[Any]) -> dict[str, Any]:
        section_titles: list[str] = []
        key_points: list[str] = []
        citations: list[str] = []
        citation_re = re.compile(r"【文献\s*0*(\d+)】")

        for block in sorted(blocks, key=lambda item: item.block_index):
            normalized_json = block.normalized_json or {}
            block_title = normalized_json.get("block_title") or block.block_title
            section_titles.append(str(block_title))
            for element in normalized_json.get("content", []):
                text = (element.get("text") or "").strip()
                if not text:
                    continue
                if len(key_points) < 10:
                    key_points.append(text[:160])
                for match in citation_re.findall(text):
                    token = f"文献{str(int(match)).zfill(2)}"
                    if token not in citations:
                        citations.append(token)

        return {
            "covered_blocks": [block.block_index for block in sorted(blocks, key=lambda item: item.block_index)],
            "section_titles": section_titles,
            "key_points": key_points,
            "used_citations": citations,
            "summary_instruction": "请基于以上压缩信息生成摘要，不要逐句复写正文。",
        }

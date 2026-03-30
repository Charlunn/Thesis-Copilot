# 数据契约与 JSON 协议

## 1. 工作区目录

每个项目对应一个独立工作区：

```text
QNU_Copilot_Workspace/
├── state.json
├── raw_pdfs/
├── processed_pdfs/
├── prompt_exports/
├── ai_outputs/
└── output/
```

目录说明：

- `state.json`
  项目唯一事实源
- `raw_pdfs/`
  用户原始拖入的 PDF 备份
- `processed_pdfs/`
  供 `NotebookLM` 使用的规范化 PDF
- `prompt_exports/`
  各阶段生成的 Prompt 文本快照
- `ai_outputs/`
  用户粘贴的原始 AI 返回内容快照
- `output/`
  最终 `.docx` 和导出日志

## 2. state.json 顶层结构

```json
{
  "project_id": "qnu-20260327-001",
  "created_at": "2026-03-27T16:00:00+08:00",
  "updated_at": "2026-03-27T16:00:00+08:00",
  "app_version": "0.1.0",
  "template_id": "qnu-undergraduate-v1",
  "workflow_stage": "references",
  "project": {
    "title": "基于XXX的物联网水质检测系统",
    "core_idea": "......",
    "discipline": "物联网工程",
    "keywords": ["物联网", "水质检测"],
    "need_reference_recommendation": true,
    "minimum_total_words": 12000
  },
  "references": {
    "source_mode": "recommended",
    "minimum_required": 20,
    "recommended_items": [],
    "bibtex_entries": [],
    "processed_items": [],
    "next_sequence": 1
  },
  "outline": {
    "system_prompt_version": "outline-v1",
    "user_prompt_text": "",
    "raw_ai_text": "",
    "normalized_json": null,
    "confirmed_tree": null,
    "status": "pending"
  },
  "chunk_plan": {
    "system_prompt_version": "chunk-plan-v1",
    "user_prompt_text": "",
    "raw_ai_text": "",
    "normalized_json": null,
    "status": "pending"
  },
  "generation": {
    "current_block_index": 0,
    "blocks": [],
    "latest_compressed_context": null,
    "status": "pending"
  },
  "export": {
    "last_docx_path": "",
    "last_exported_at": "",
    "status": "pending"
  },
  "ui": {
    "last_route": "",
    "notices_dismissed": []
  }
}
```

## 3. references 模块

### 3.1 recommended_items

```json
[
  {
    "source_index": 1,
    "title": "论文标题",
    "language": "zh",
    "download_url": "https://example.com/paper.pdf",
    "venue": "某期刊/会议",
    "year": 2024,
    "impact_note": "推荐理由",
    "bibtex_key": "zhang2024example",
    "status": "pending"
  }
]
```

`status` 枚举建议：

- `pending`
- `imported`
- `skipped_unavailable`
- `skipped_user_choice`
- `match_failed`

### 3.2 processed_items

```json
[
  {
    "effective_index": 1,
    "source_index": 2,
    "title": "论文标题",
    "normalized_title": "论文标题",
    "language": "en",
    "raw_pdf_path": "raw_pdfs/original-name.pdf",
    "processed_pdf_path": "processed_pdfs/01_论文标题.pdf",
    "file_size": 1234567,
    "sha256": "......",
    "bibtex_key": "smith2023example"
  }
]
```

说明：

- `source_index` 表示推荐列表中的原始顺序
- `effective_index` 表示最终有效编号，用于文件名前缀和引用映射

## 4. 文件命名规则

规范化文件名：

```text
{effective_index:02d}_{sanitized_title}.pdf
```

需要执行：

- 去除 Windows 非法字符 `< > : " / \ | ? *`
- 去除首尾空格和句点
- 合并连续空白
- 控制标题片段长度，避免路径过长
- 同名时追加短哈希或年份

跳过某篇论文时：

- `source_index` 保留
- `effective_index` 不分配
- `next_sequence` 不增加

## 5. AI 阶段协议

所有阶段都应保留三份内容：

- 原始粘贴文本 `raw_ai_text`
- 清洗后的 JSON 字符串 `normalized_json_text`
- 解析后的结构对象 `normalized_json`

## 5.1 文献推荐 JSON

```json
{
  "topic": "研究主题",
  "papers": [
    {
      "title": "论文标题",
      "language": "zh",
      "year": 2024,
      "venue": "期刊或会议",
      "download_url": "https://example.com/paper.pdf",
      "impact_note": "推荐理由",
      "bibtex": "@article{...}"
    }
  ]
}
```

校验规则：

- `papers.length >= 30`
- 中文不少于 15 篇
- 英文不少于 15 篇
- 每项必须包含 `title`、`language`、`download_url`、`bibtex`

## 5.2 大纲 JSON

建议协议：

```json
{
  "title": "论文标题",
  "outline": [
    {
      "id": "1",
      "level": 1,
      "title": "绪论",
      "children": [
        {
          "id": "1.1",
          "level": 2,
          "title": "研究背景",
          "children": []
        }
      ]
    }
  ]
}
```

校验规则：

- 根层节点至少 3 个
- `level` 必须与层级一致
- `id` 必须可稳定排序
- 不允许出现空标题

软件内部可在确认后补充扩展字段：

```json
{
  "must_be_separate_block": false,
  "enabled": true
}
```

## 5.3 切块规划 JSON

```json
{
  "total_blocks": 8,
  "blocks": [
    {
      "block_index": 1,
      "title": "绪论与研究背景",
      "outline_node_ids": ["1", "1.1", "1.2"],
      "goal": "交代研究背景、问题定义与研究意义",
      "minimum_words": 1200,
      "citation_focus": ["文献综述", "相关系统"]
    }
  ]
}
```

校验规则：

- `blocks.length === total_blocks`
- `block_index` 连续且从 1 开始
- 所有启用的大纲节点必须至少被一个块覆盖
- `minimum_words` 总和不低于用户设置的最低总字数

## 5.4 正文块 JSON

为兼容模板注入和后续排版，正文块采用扁平段落协议：

```json
{
  "block_index": 1,
  "block_title": "绪论与研究背景",
  "content": [
    {
      "type": "h1",
      "text": "第1章 绪论"
    },
    {
      "type": "h2",
      "text": "1.1 研究背景"
    },
    {
      "type": "p",
      "text": "随着......【文献01】"
    },
    {
      "type": "list",
      "items": ["要点A", "要点B"]
    },
    {
      "type": "table_placeholder",
      "text": "表1-1 某某参数对比"
    }
  ]
}
```

校验规则：

- `block_index` 与当前轮次一致
- `content` 不能为空
- `type` 仅允许：
  - `h1`
  - `h2`
  - `h3`
  - `p`
  - `list`
  - `table_placeholder`
- 所有文本字段必须是字符串

## 5.5 脱水压缩 JSON

```json
{
  "covered_blocks": [1, 2, 3],
  "compressed_context": {
    "narrative_summary": "前文已完成......",
    "key_claims": [
      "已经定义了研究问题",
      "已经说明了系统目标"
    ],
    "used_citations": ["文献01", "文献03"],
    "pending_topics": [
      "实验设计",
      "结果分析"
    ],
    "style_constraints": [
      "保持学术口吻",
      "避免与前文重复"
    ]
  }
}
```

校验规则：

- `covered_blocks` 必须覆盖当前已完成全部块
- `narrative_summary` 非空
- `pending_topics` 与后续块目标不能冲突

## 6. 解析与容错流水线

所有阶段统一走以下清洗顺序：

1. 保存原始文本到 `ai_outputs/`
2. 去除 Markdown 代码块标记
3. 截取首个合法 JSON 对象或数组起始位置
4. 尝试补齐单个缺失的尾部 `]` 或 `}`
5. 尝试将中文全角引号替换为半角引号
6. 执行 Schema 校验
7. 失败则给用户展示错误摘要和修复建议

注意：

- 不建议做激进的自动语义修复
- 不允许静默篡改关键字段含义

## 7. 引用重映射规则

正文生成阶段允许 AI 使用临时占位符：

```text
【文献01】
【文献02】
```

最终导出前：

1. 根据 `processed_items` 的 `effective_index` 建立映射
2. 将 `【文献XX】` 转为最终序号
3. 再由 Word 渲染层决定是否显示为上标

如果正文引用了不存在的文献编号：

- 标记导出警告
- 允许用户继续导出
- 在日志中记录缺失项

## 8. 状态枚举建议

常用状态：

- `pending`
- `ready`
- `in_progress`
- `completed`
- `failed`
- `needs_review`

工作流阶段建议：

- `project_init`
- `references`
- `pdf_processing`
- `outline_generation`
- `outline_editing`
- `chunk_planning`
- `block_generation`
- `export`
- `done`

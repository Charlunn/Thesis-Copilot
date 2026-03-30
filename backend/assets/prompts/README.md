# Prompt 模板资产

本目录包含所有 Prompt 模板的统一版本管理。每个 Prompt 都有明确的模型提示和操作说明。

## 文件说明

| 文件 | 类型 | 用途 | 适用模型 |
|------|------|------|----------|
| `reference_recommendation.json` | reference_recommendation | 文献推荐 | 通用 LLM |
| `outline.json` | outline | 大纲生成 | NotebookLM |
| `chunk_plan.json` | chunk_plan | 切块规划 | 通用 LLM |
| `block_generation.json` | block_generation | 正文块生成 | NotebookLM |
| `compression.json` | compression | 上下文压缩 | 通用 LLM |

## 模板结构

每个 JSON 文件包含：

```json
{
  "version": "v1",
  "type": "prompt 类型标识",
  "description": "Prompt 描述",
  "model_hint": "推荐使用的模型",
  "instructions": ["操作步骤说明"],
  "template": "Prompt 模板内容"
}
```

## 使用说明

- `model_hint`: 告知用户应该使用哪个模型
- `instructions`: 明确操作步骤，让用户知道该做什么
- `template`: 实际的 Prompt 模板，支持变量占位符

# QNU Thesis Copilot

青师大毕设辅助写作与自动化排版系统的半自动桌面端 MVP 规格仓库。

当前阶段目标不是做全自动 SaaS，也不是做开放模板平台，而是先做一个可以给朋友和同校同学稳定使用的、本地优先的桌面工具：

- 固定青海师范大学论文模板
- 软件本体不直连任何模型 API
- 用户手动与 `NotebookLM` / 通用 LLM 交互
- 本地完成 PDF 资产整理、流程编排、JSON 校验、引用还原和 Word 导出

## 当前结构

- `backend/`
  Python 本地内核与 FastAPI 适配层
  - `src/qnu_copilot/` - 核心服务模块
    - `services/` - 14 个服务模块（workspace, references, outline, chunk_plan, generation, export, backup, prompts, contracts, errors, logging, filesystem, template_checker, aigc）
    - `api/` - API 路由
    - `domain/` - 领域模型
  - `tests/` - 后端单元/集成测试
  - `assets/`
    - `prompts/` - 7 个 Prompt 模板（大纲生成、切块规划、正文生成、压缩、文献推荐等）
    - `templates/qnu-undergraduate-v1.docx` - **青海师范大学正式模板已接入** ✅

- `desktop/`
  Electron + React 桌面壳
  - `src/components/` - 7 个核心组件（AIGCPanel, APISettingsPanel, ChunkPlanEditor, GenerationWorkbench, OutlineTreeEditor, ProjectListPanel, PromptPreviewCard）
  - `App.tsx` - 主应用

- `docs/`
  - `mvp-spec.md` - MVP 产品规格
  - `data-contracts.md` - 数据模型与 JSON 协议
  - `implementation-notes.md` - 技术架构与实现建议
  - `optimization-plan.md` - 优化方向与优先级
  - `technical-report.md` - 技术报告
  - `work-report.md` - 述职报告

## 当前版本的产品定位

这是一个"强教学、强约束、强流程"的论文协作工具。

软件的职责不是代替用户思考，而是把已经验证有效的人机协作链条固定下来：

1. 用户提供题目、核心思想和文献素材
2. 软件生成每一步该发给哪个模型的 Prompt
3. 用户把 AI 返回的 JSON 粘贴回软件
4. 软件解析、校验、保存进度并驱动下一步
5. 最终用本地模板引擎导出 `.docx`

## 当前实现进度

✅ **MVP 主闭环已完整实现**：

### 后端服务 (14 个模块)
- ✅ 项目创建、恢复与工作区切换
- ✅ 推荐文献 JSON 导入与校验
- ✅ PDF 逐篇/批量导入与连续编号
- ✅ BibTeX 导入与关联
- ✅ 大纲导入与确认
- ✅ 切块规划导入与确认
- ✅ 正文块逐块生成与压缩
- ✅ 本地 `.docx` 导出（含正式模板注入）
- ✅ 项目备份与恢复
- ✅ Prompt 模板管理与渲染
- ✅ 数据契约校验
- ✅ 错误处理与日志
- ✅ 模板检查器
- ✅ AIGC 相关服务

### 前端组件 (7 个组件)
- ✅ 项目列表与工作区选择
- ✅ 大纲树编辑器
- ✅ 切块规划编辑器
- ✅ 正文生成工作台
- ✅ PDF 处理界面
- ✅ BibTeX 导入界面
- ✅ API 设置面板
- ✅ 导出历史展示

### Prompt 模板 (7 个)
- ✅ outline.json - 大纲生成模板
- ✅ chunk_plan.json - 切块规划模板
- ✅ block_generation.json - 正文块生成模板
- ✅ compression.json - 上下文压缩模板
- ✅ reference_recommendation.json - 文献推荐模板
- ✅ aigc_reduction.json - AIGC 降重模板
- ✅ README.md - 模板说明

### 测试覆盖
- ✅ test_workspace.py - 工作区测试
- ✅ test_references.py - 文献处理测试
- ✅ test_outline.py - 大纲测试
- ✅ test_chunk_generation.py - 块生成测试
- ✅ test_contracts.py - 数据契约测试
- ✅ test_api.py - API 集成测试

### 关键里程碑
- ✅ **正式学校模板已接入** (`qnu-undergraduate-v1.docx`)
- ✅ 导出时优先使用正式模板
- ✅ 若模板不存在则回退到基础样式导出

## MVP 的关键原则

- `NotebookLM` 只用于依赖 PDF 事实锚定的步骤
- 通用 LLM 只用于脱水、补全、规划、格式修复等辅助任务
- 所有 AI 回传结果优先使用 JSON 协议
- `state.json` 是项目唯一事实源
- 引用编号以"成功进入本地工作区的 PDF 顺序"为准

## 本地运行

后端测试：

```bash
cd backend
python -B -m pytest -p no:cacheprovider
```

桌面端开发：

```bash
cd desktop
npm install
npm run dev
```

桌面端构建：

```bash
cd desktop
npm run build
```

## 技术栈

- **后端**: Python 3.10+ / FastAPI / Pydantic / python-docx
- **前端**: Electron / React / TypeScript / Vite
- **模板**: 青海师范大学本科毕业论文模板 (qnu-undergraduate-v1)
- **数据**: 本地工作区 + state.json

## 下一步优化方向

详见 `docs/optimization-plan.md`，主要方向：

- 参考文献 GB/T 7714 格式优化
- 块生成质量校验增强
- 导出结构完整性检查
- UI 教学引导优化
- 项目分享包导出
- Windows 安装包打包

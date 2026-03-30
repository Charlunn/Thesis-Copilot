# QNU Thesis Copilot 技术报告

## 1. 项目背景

传统通用 AI 在论文写作场景中常见的问题包括：

- 长文生成时逻辑崩塌
- 文献引用不稳定
- 输出格式无法程序化控制
- 最终 Word 排版与学校要求不一致

QNU Thesis Copilot 的目标，是把"NotebookLM + 通用 LLM + 本地脚本"的有效协作经验产品化，形成一个本地优先、强流程约束的桌面端 MVP。

## 2. 系统目标

本项目并不追求"一键全自动生成论文"，而是强调：

- 对不同模型进行能力边界拆分
- 通过 JSON 协议固定中间产物
- 用本地状态机驱动人机协作
- 在最终阶段完成本地导出

## 3. 总体架构

系统采用双进程桌面架构：

### 3.1 桌面壳

- 技术：Electron + React + TypeScript + Vite
- 职责：阶段式页面、文件选择、工作区切换、项目恢复、结果展示
- 核心组件：
  - `ProjectListPanel` - 项目列表与工作区管理
  - `OutlineTreeEditor` - 大纲树编辑器
  - `ChunkPlanEditor` - 切块规划编辑器
  - `GenerationWorkbench` - 正文生成工作台
  - `AIGCPanel` - AIGC 面板
  - `APISettingsPanel` - API 设置

### 3.2 本地内核

- 技术：Python + FastAPI + Pydantic
- 职责：状态管理、PDF 处理、JSON 校验、Prompt 组装、BibTeX 管理、导出
- 核心服务模块（14 个）：
  - `workspace` - 工作区创建、项目管理、目录结构
  - `references` - 推荐文献导入、PDF 处理、编号管理
  - `outline` - 大纲 JSON 导入、树结构转换
  - `chunk_plan` - 切块规划导入、覆盖检查
  - `generation` - 正文块保存、上下文压缩
  - `export` - `.docx` 导出、模板注入、引用重映射
  - `backup` - 项目备份与恢复
  - `prompts` - Prompt 模板管理与渲染
  - `contracts` - 数据契约定义与校验
  - `errors` - 统一错误处理
  - `logging` - 日志记录
  - `filesystem` - 文件系统操作
  - `template_checker` - 模板文件检查
  - `aigc` - AIGC 相关服务

### 3.3 数据存储

- 采用本地工作区
- 每个项目以 `state.json` 为唯一事实源
- PDF、Prompt 快照、AI 输出、导出文件均在本地目录持久化

## 4. 关键技术设计

## 4.1 工作流状态机

项目状态按阶段推进：

- `references` → `pdf_processing` → `outline_generation` → `outline_editing` → `chunk_planning` → `block_generation` → `export` → `done`

这一设计保证用户不会在错误阶段执行错误操作，也使项目恢复变得可控。

## 4.2 JSON 合同与清洗

系统对以下结构建立了固定合同：

- 参考文献推荐
- 大纲
- 切块规划
- 正文块
- 压缩上下文

清洗流程统一处理：

- Markdown 代码块包裹
- 前后解释性文本
- 尾部单个括号缺失
- 常见引号问题

随后再进入 Pydantic 校验，避免不稳定输出直接污染状态。

## 4.3 PDF 资产处理

PDF 管理的关键规则包括：

- 连续编号
- 标题规范化
- 非法字符清洗
- 重名冲突处理
- 哈希去重

这样做的目的，是把 AI 侧文献编号、磁盘文件名、最终引用顺序统一起来。

## 4.4 Prompt 本地拼装

系统没有把"下一块 Prompt"交给通用 LLM 自由生成，而是坚持本地模板拼装：

- 通用 LLM 只返回结构化 `compressed_context`
- NotebookLM 的下一块 Prompt 始终由本地程序生成

这一设计显著降低了后续轮次的漂移风险，也提升了可调试性。

## 4.5 BibTeX 与导出

本阶段新增了两项关键能力：

### BibTeX 导入

- 支持从推荐文献链路自动提取
- 支持用户手动粘贴完整 BibTeX 覆盖或补充
- 会尝试按 `key` 或标题将 BibTeX 与已处理文献关联

### 导出服务

- 校验所有正文块是否完成
- 汇总块级 JSON 内容
- 将 `【文献XX】` 还原为本地顺序引用
- 基于 `python-docx` 生成 `.docx`
- **✅ 若存在固定模板文件 `qnu-undergraduate-v1.docx`，则使用正式模板注入**
- 同时生成导出日志文件，便于追踪问题

## 5. 资源资产

### 5.1 Prompt 模板

项目内置 7 个 Prompt 模板，统一存放于 `backend/assets/prompts/`：

- `outline.json` - 大纲生成模板
- `chunk_plan.json` - 切块规划模板
- `block_generation.json` - 正文块生成模板
- `compression.json` - 上下文压缩模板
- `reference_recommendation.json` - 文献推荐模板
- `aigc_reduction.json` - AIGC 降重模板

### 5.2 论文模板

- **✅ 青海师范大学正式模板已接入**：`backend/assets/templates/qnu-undergraduate-v1.docx`
- 导出时优先使用正式模板
- 若模板不存在则回退到基础样式导出

## 6. 当前实现结果

截至当前版本，系统已经完整实现：

### 后端服务 (14 个模块)
- ✅ 项目创建与恢复
- ✅ 推荐文献导入
- ✅ PDF 逐篇或批量处理
- ✅ 大纲导入与确认
- ✅ 切块规划导入与确认
- ✅ 正文块逐块生成与压缩
- ✅ BibTeX 手动导入
- ✅ **本地 `.docx` 导出（含正式模板注入）**
- ✅ 项目备份与恢复
- ✅ Prompt 模板统一管理
- ✅ 数据契约校验
- ✅ 统一错误处理与日志
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

这意味着 MVP 已经具备从"项目初始化"到"文档导出"的完整闭环，**且已接入青海师范大学正式模板**。

## 7. 测试与验证

项目当前包含后端单元/集成测试和桌面端类型/构建校验。

已验证内容包括：

- 工作区与状态文件创建
- 推荐文献导入与 PDF 连续编号
- 大纲导入与确认
- 切块规划与正文生成链路
- BibTeX 导入接口
- **`.docx` 导出接口（含模板注入）**
- Electron preload 与桌面端构建

## 8. 当前局限

目前系统仍有以下工程性局限：

- 参考文献格式化为工程化近似方案，未完全达到严格标准化 GB/T 7714 输出
- 前端主页面职责较多，后续需要进一步组件化
- 尚未提供安装包和自动更新机制

## 9. 后续演进方向

### 9.1 面向校内试用

- 进一步提升导出样式质量
- 增强错误提示和导出历史
- 打包 Windows 安装版本
- 组织校内小范围试用，收集反馈后迭代

### 9.2 面向全自动版本

- 在 Python 端保留 Router 接缝
- 未来可将手动 Prompt 流程切换为 API 调度
- `state.json` 与服务层已具备继续自动化的基础

## 10. 结论

QNU Thesis Copilot 当前版本已经完成了一个有清晰架构边界、能稳定运行、**具备完整导出闭环且已接入青海师范大学正式模板**的半自动桌面端 MVP。它既能支撑现实使用，也能作为后续全自动版本和校内推广版本的工程基础。

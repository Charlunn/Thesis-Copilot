# 实现建议与开发顺序

## 1. 技术形态

建议采用桌面端双进程架构：

- UI：Electron + React
- 本地逻辑层：Python 3.10+

原因：

- 你现有的 Word 生成脚本更适合直接复用 Python
- Electron 适合做剪贴板、拖拽上传、文件选择、安装包分发
- 桌面端天然符合“本地优先、不给 API Key、先给熟人使用”的目标

## 2. 架构分层

### 2.1 Electron 主进程

负责：

- 启动和守护 Python sidecar
- 管理窗口生命周期
- 文件系统权限桥接
- 剪贴板操作

### 2.2 Electron 渲染进程

负责：

- 向导式页面
- 树编辑器
- JSON 粘贴和错误展示
- PDF 拖拽交互
- 导出结果展示

### 2.3 Python sidecar

负责：

- `state.json` 读写
- PDF 复制、重命名、哈希计算
- JSON 清洗与 Schema 校验
- BibTeX 解析与参考文献格式化
- Word 模板注入与导出

## 3. 模块切分建议

Python 端建议最少拆成以下模块：

- `workspace_manager`
  创建项目、维护目录、读写状态
- `reference_service`
  推荐列表导入、PDF 处理、编号补位
- `json_contracts`
  所有阶段的 Schema 校验和清洗
- `outline_service`
  大纲导入、树结构转换
- `chunk_service`
  切块规划导入、覆盖检查
- `generation_service`
  正文块保存、上下文压缩结果保存
- `citation_service`
  引用重映射
- `docx_service`
  复用 `qnu_thesis_builder` 逻辑输出文档

## 4. Prompt 模板管理

建议不要把 Prompt 写死在页面组件里，而是统一管理。

建议建立本地模板目录：

```text
assets/prompts/
├── recommend_references.md
├── notebooklm_outline_system.md
├── notebooklm_outline_user.md
├── chunk_plan_user.md
├── block_generate_user.md
└── compress_context_user.md
```

模板渲染策略：

- 使用占位符变量，如 `{{title}}`、`{{core_idea}}`
- 由 Python 或前端统一渲染
- 每次渲染后的最终 Prompt 存档到 `prompt_exports/`

## 5. 为什么“下一块 Prompt”应由软件本地拼装

不建议让通用 LLM 直接生成给 `NotebookLM` 的下一块完整 Prompt，原因有三：

1. 容易漂移，后面越生成越偏离你的原始模板
2. 不利于调试，出了问题很难判断是模板错还是模型自由发挥
3. 不利于版本控制，无法稳定复现实验结果

更稳的方式是：

- 通用 LLM 只返回结构化 `compressed_context`
- 软件使用固定模板 + 当前项目状态，拼出下一块 Prompt

## 6. MVP 建议开发顺序

### 里程碑 1：本地工作区闭环

先完成：

- 工作区创建
- `state.json`
- PDF 拖拽与重命名
- 项目恢复

完成标准：

- 用户可以新建项目并得到规范化 PDF 文件夹

### 里程碑 2：大纲与导出闭环

再完成：

- 大纲 JSON 导入
- 大纲树编辑
- BibTeX 导入
- Word 模板导出

完成标准：

- 即使正文由外部生成，软件也能完成结构编辑和文档导出

### 里程碑 3：完整半自动循环

最后补：

- 切块规划
- 块生成工作台
- 上下文脱水链路
- 阶段状态恢复

完成标准：

- 用户能在软件引导下完成整篇论文的多轮半自动生成

## 7. 安装与分发建议

第一版优先考虑 Windows：

- Electron 使用 `electron-builder`
- Python sidecar 使用 PyInstaller 打包
- 模板文件随安装包内置

暂时不需要：

- 自动更新
- 多平台签名
- 高强度加密壳

## 8. 现在最值得马上做的事

代码层面最推荐的第一步不是先写 UI，而是先把下面三件事做成可调用模块：

1. 创建工作区与写入 `state.json`
2. 处理单篇或批量 PDF，产出规范命名结果
3. 校验“大纲 JSON / 切块 JSON / 正文块 JSON”

这三件事一旦稳定，前端只是把这些能力包起来。

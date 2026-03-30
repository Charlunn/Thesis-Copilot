# QNU Thesis Copilot MVP 增强规划

## 版本目标
完善 MVP 版本，增加预览、数据管理、用户体验和稳定性功能。

---

## P0 - 核心体验（必须完成）

### 1. 论文预览服务
**文件**: `backend/src/qnu_copilot/services/preview.py`

```python
class PreviewService:
    """生成论文 HTML/Markdown 预览"""
    
    def generate_html_preview(project_id: str) -> str:
        """生成可预览的 HTML"""
        
    def generate_markdown_preview(project_id: str) -> str:
        """生成 Markdown 格式"""
        
    def get_preview_history(project_id: str) -> list[PreviewSnapshot]:
        """获取历史预览快照"""
```

**API 端点**:
- `GET /projects/{project_id}/preview` - 获取当前预览
- `GET /projects/{project_id}/preview/history` - 预览历史

**前端组件**: `desktop/src/components/PreviewPanel.tsx`
- 集成到导出区域旁边
- 支持切换预览格式（HTML/Markdown）
- 实时更新按钮

---

### 2. 项目导入/导出与回滚
**文件**: `backend/src/qnu_copilot/services/archive.py`

```python
class ArchiveService:
    """项目打包与恢复"""
    
    def export_project_archive(project_id: str, output_path: str) -> str:
        """导出项目为压缩包"""
        
    def import_project_archive(archive_path: str) -> str:
        """导入项目压缩包"""
        
    def get_backup_list(project_id: str) -> list[BackupInfo]:
        """获取备份列表"""
        
    def rollback_to_backup(project_id: str, backup_id: str) -> bool:
        """回滚到指定备份"""
```

**API 端点**:
- `POST /projects/{project_id}/archive/export` - 导出项目包
- `POST /projects/archive/import` - 导入项目包
- `GET /projects/{project_id}/backups` - 获取备份列表
- `POST /projects/{project_id}/backups/{backup_id}/rollback` - 回滚

**前端组件**: `desktop/src/components/ArchivePanel.tsx`
- 项目列表页添加"导出项目"按钮
- 工作区设置添加"导入项目"按钮
- 备份管理面板

---

## P1 - 用户体验提升

### 3. 逐块生成队列与连贯性保证
**文件**: `backend/src/qnu_copilot/services/generation_queue.py`

```python
class GenerationQueueService:
    """批量生成队列"""
    
    def enqueue_blocks(project_id: str, block_indices: list[int]) -> str:
        """将多个块加入队列"""
        
    def process_next(project_id: str) -> GenerationTask:
        """处理下一个任务"""
        
    def get_queue_status(project_id: str) -> QueueStatus:
        """获取队列状态"""
        
    def ensure_coherence(previous_block: str, current_block: str) -> str:
        """确保块之间的连贯性"""
```

**改进内容**:
- 新增批量生成按钮
- 进度条显示
- 自动连贯性检查
- 失败重试机制

**前端组件**: `desktop/src/components/GenerationQueue.tsx`

---

### 4. 教程与工具提示
**文件**: 
- `backend/assets/tutorials/` - 教程内容
- `desktop/src/components/TooltipGuide.tsx`
- `desktop/src/data/tutorials.json`

**教程内容**:
1. 首次使用引导（3步）
2. 论文生成完整流程
3. 各阶段详细说明
4. 常见问题解答

**工具提示**:
- 每个功能添加 `helpText` 字段
- 悬浮显示详细说明
- 首次使用高亮提示

---

### 5. PDF 处理异步化
**文件**: `backend/src/qnu_copilot/services/async_processor.py`

```python
class AsyncPDFProcessor:
    """后台 PDF 处理"""
    
    def submit_batch(project_id: str, pdf_paths: list[str]) -> str:
        """提交批量任务，返回任务ID"""
        
    def get_task_status(task_id: str) -> TaskStatus:
        """获取任务状态"""
        
    def cancel_task(task_id: str) -> bool:
        """取消任务"""
```

**后台任务系统**:
- 使用 `asyncio` + 后台线程
- 任务状态: pending → processing → completed/failed
- 进度回调通知前端

**API 端点**:
- `POST /projects/{project_id}/pdf/batch-async` - 异步批量处理
- `GET /tasks/{task_id}` - 获取任务状态
- `DELETE /tasks/{task_id}` - 取消任务

**前端**: 任务进度条 + 后台通知

---

## P2 - 性能与稳定性

### 6. 缓存系统
**文件**: `backend/src/qnu_copilot/services/cache.py`

```python
class CacheService:
    """智能缓存"""
    
    def get_pdf_cache(pdf_hash: str) -> str | None:
        """获取 PDF 缓存"""
        
    def set_pdf_cache(pdf_hash: str, content: str) -> None:
        """设置 PDF 缓存"""
        
    def get_prompt_cache(prompt_hash: str) -> str | None:
        """获取 Prompt 缓存"""
        
    def invalidate(pattern: str) -> None:
        """清除匹配的缓存"""
```

**缓存策略**:
- PDF 内容缓存（按 SHA256）
- Prompt 渲染结果缓存
- 自动过期清理（7天）
- 手动清除功能

---

### 7. 测试覆盖
**文件**: `backend/tests/`

```
tests/
├── unit/
│   ├── test_aigc.py
│   ├── test_backup.py
│   ├── test_export.py
│   ├── test_generation.py
│   └── test_contracts.py
├── integration/
│   ├── test_api_projects.py
│   ├── test_api_export.py
│   └── test_workflow.py
└── conftest.py
```

**测试用例**:
- 单元测试: 服务类核心方法
- 集成测试: API 端点
- 端到端测试: 完整工作流

**覆盖率目标**: 核心服务 > 80%

---

## P3 - 文档与部署

### 8. 用户文档
**文件**: `docs/user-guide.md`

- 安装指南
- 快速开始
- 各功能详细说明
- 常见问题
- 最佳实践

### 9. 部署脚本优化
**文件**: `scripts/`
- `build-windows.ps1` - Windows 构建
- `build-unix.sh` - Unix 构建
- `deploy.sh` - 一键部署

---

## 开发优先级与时间估计

| 优先级 | 功能 | 复杂度 | 估计工时 |
|--------|------|--------|----------|
| P0 | 论文预览服务 | 中 | 8h |
| P0 | 导入/导出/回滚 | 中 | 10h |
| P1 | 批量生成队列 | 高 | 12h |
| P1 | 教程系统 | 低 | 6h |
| P1 | 工具提示 | 低 | 4h |
| P1 | PDF 异步处理 | 高 | 10h |
| P2 | 缓存系统 | 中 | 6h |
| P2 | 测试覆盖 | 中 | 8h |
| P3 | 用户文档 | 低 | 4h |

**总计**: 约 68 小时

---

## 实施建议

### 阶段一：P0 功能（1-2天）
1. 实现 PreviewService
2. 实现 ArchiveService
3. 前端集成预览和导出面板

### 阶段二：P1 核心体验（2-3天）
1. 批量生成队列
2. PDF 异步处理
3. 教程和工具提示

### 阶段三：P2 稳定性和测试（2天）
1. 缓存系统
2. 测试用例编写
3. Bug 修复

### 阶段四：P3 收尾（1天）
1. 用户文档
2. 部署脚本
3. 最终测试

---

## 技术债务

- [ ] 日志级别统一
- [ ] 异常处理统一
- [ ] API 文档生成（OpenAPI）
- [ ] 配置管理优化
- [ ] 代码注释完善

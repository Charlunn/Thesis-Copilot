import { startTransition, useEffect, useState } from "react";

import ChunkPlanEditor from "./components/ChunkPlanEditor";
import GenerationWorkbench from "./components/GenerationWorkbench";
import OutlineTreeEditor from "./components/OutlineTreeEditor";
import PromptPreviewCard from "./components/PromptPreviewCard";
import ProjectListPanel from "./components/ProjectListPanel";
import APISettingsPanel from "./components/APISettingsPanel";
import AIGCPanel from "./components/AIGCPanel";
import type {
  ChunkPlan,
  ConfirmedOutlineTree,
  ExportHistoryItem,
  ExportProjectResult,
  GeneratedBlockState,
  ProjectListItem,
  ProjectStateResponse,
  PromptPreviewResponse,
} from "./types";

const initialProjectForm = {
  title: "",
  coreIdea: "",
  needReferenceRecommendation: true,
  minimumRequiredReferences: 20,
  minimumTotalWords: "",
};

type AppInfo = Awaited<ReturnType<typeof window.qnuCopilot.getAppInfo>>;
type BannerState = { type: "info" | "success" | "error"; text: string } | null;
type UiStep =
  | "project"
  | "recommendation"
  | "pdf"
  | "bibtex"
  | "outline"
  | "chunk"
  | "generation"
  | "export"
  | "done";

function App() {
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);
  const [backendStatus, setBackendStatus] = useState<"checking" | "ready" | "error">("checking");
  const [banner, setBanner] = useState<BannerState>(null);
  const [busyLabel, setBusyLabel] = useState("");
  const [projectForm, setProjectForm] = useState(initialProjectForm);
  const [projectIdInput, setProjectIdInput] = useState("");
  const [projectList, setProjectList] = useState<ProjectListItem[]>([]);
  const [currentProject, setCurrentProject] = useState<ProjectStateResponse | null>(null);
  const [showStatusInfo, setShowStatusInfo] = useState(false);
  const [recommendationRawText, setRecommendationRawText] = useState("");
  const [recommendationPrompt, setRecommendationPrompt] = useState<PromptPreviewResponse | null>(null);
  const [outlineRawText, setOutlineRawText] = useState("");
  const [outlineDraft, setOutlineDraft] = useState<ConfirmedOutlineTree | null>(null);
  const [outlinePrompt, setOutlinePrompt] = useState<PromptPreviewResponse | null>(null);
  const [chunkPlanRawText, setChunkPlanRawText] = useState("");
  const [chunkPlanDraft, setChunkPlanDraft] = useState<ChunkPlan | null>(null);
  const [chunkPlanPrompt, setChunkPlanPrompt] = useState<PromptPreviewResponse | null>(null);
  const [blockPrompt, setBlockPrompt] = useState<PromptPreviewResponse | null>(null);
  const [compressPrompt, setCompressPrompt] = useState<PromptPreviewResponse | null>(null);
  const [blockRawText, setBlockRawText] = useState("");
  const [compressRawText, setCompressRawText] = useState("");
  const [bibtexRawText, setBibtexRawText] = useState("");
  const [exportFilename, setExportFilename] = useState("");
  const [lastExportResult, setLastExportResult] = useState<ExportProjectResult | null>(null);
  const [lastReviewItems, setLastReviewItems] = useState<{ file_path: string; reason: string }[]>([]);
  const [showAPISettings, setShowAPISettings] = useState(false);

  useEffect(() => {
    let active = true;

    const checkBackend = async () => {
      try {
        const [info, , projectListResponse] = await Promise.all([
          window.qnuCopilot.getAppInfo(),
          window.qnuCopilot.health(),
          window.qnuCopilot.listProjects(),
        ]);
        if (!active) {
          return;
        }
        setAppInfo(info);
        setProjectList(projectListResponse.projects);
        setBackendStatus("ready");

        const fallbackProjectId = projectListResponse.projects[0]?.project_id ?? "";
        const preferredProjectId =
          info.lastProjectId &&
          projectListResponse.projects.some((project) => project.project_id === info.lastProjectId)
            ? info.lastProjectId
            : fallbackProjectId;

        if (!preferredProjectId) {
          return;
        }
        try {
          const projectResponse = await window.qnuCopilot.getProject(preferredProjectId);
          if (!active) {
            return;
          }
          syncCurrentProject(projectResponse);
          setBanner({
            type: "info",
            text: `已恢复上次项目：${projectResponse.state.project.title}`,
          });
        } catch {
          if (!active) {
            return;
          }
          void window.qnuCopilot.setLastProjectId("");
        }
      } catch (error) {
        if (!active) {
          return;
        }
        setBackendStatus("error");
        setBanner({
          type: "error",
          text: getErrorMessage(error, "本地后端未能启动，请检查 Python 环境或启动日志。"),
        });
      }
    };

    void checkBackend();
    return () => {
      active = false;
    };
  }, []);

  async function refreshProjectList() {
    try {
      const response = await window.qnuCopilot.listProjects();
      startTransition(() => {
        setProjectList(response.projects);
      });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "刷新项目列表失败。") });
    }
  }

  function syncCurrentProject(response: ProjectStateResponse) {
    const activeProjectBlock = findGenerationBlock(
      response.state.generation.blocks,
      response.state.generation.current_block_index,
    );
    void window.qnuCopilot.setLastProjectId(response.project_id);

    startTransition(() => {
      setCurrentProject(response);
      setProjectIdInput(response.project_id);
      setRecommendationPrompt(null);
      setOutlineDraft(response.state.outline.confirmed_tree ?? null);
      setOutlineRawText(response.state.outline.raw_ai_text ?? "");
      setOutlinePrompt(null);
      setBibtexRawText(joinBibtexEntries(response));
      setChunkPlanDraft(
        response.state.chunk_plan.confirmed_plan ?? response.state.chunk_plan.normalized_json ?? null,
      );
      setChunkPlanRawText(response.state.chunk_plan.raw_ai_text ?? "");
      setChunkPlanPrompt(null);
      setBlockPrompt(null);
      setCompressPrompt(null);
      setBlockRawText(activeProjectBlock?.raw_ai_text ?? "");
      setCompressRawText(activeProjectBlock?.compressed_context_raw_ai_text ?? "");
      setExportFilename("");
      setLastExportResult(null);
    });
  }

  function clearSelectedProjectState() {
    void window.qnuCopilot.setLastProjectId("");
    startTransition(() => {
      setCurrentProject(null);
      setProjectIdInput("");
      setRecommendationRawText("");
      setRecommendationPrompt(null);
      setOutlineRawText("");
      setOutlineDraft(null);
      setOutlinePrompt(null);
      setChunkPlanRawText("");
      setChunkPlanDraft(null);
      setChunkPlanPrompt(null);
      setBlockPrompt(null);
      setCompressPrompt(null);
      setBlockRawText("");
      setCompressRawText("");
      setBibtexRawText("");
      setExportFilename("");
      setLastExportResult(null);
      setLastReviewItems([]);
    });
  }

  async function createProject() {
    setBusyLabel("正在创建项目");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.createProject({
        title: projectForm.title,
        core_idea: projectForm.coreIdea,
        need_reference_recommendation: projectForm.needReferenceRecommendation,
        minimum_required_references: Math.max(1, Number(projectForm.minimumRequiredReferences || 1)),
        minimum_total_words: projectForm.minimumTotalWords
          ? Number(projectForm.minimumTotalWords)
          : null,
      });
      syncCurrentProject(response);
      startTransition(() => {
        setRecommendationRawText("");
        setLastReviewItems([]);
      });
      await refreshProjectList();
      setBanner({ type: "success", text: `项目已创建：${response.project_id}` });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "创建项目失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function loadProject() {
    await loadProjectById(projectIdInput.trim());
  }

  async function loadProjectById(projectId: string) {
    if (!projectId) {
      setBanner({ type: "error", text: "请先输入项目 ID。" });
      return;
    }
    setBusyLabel("正在载入项目");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.getProject(projectId);
      syncCurrentProject(response);
      startTransition(() => {
        setRecommendationRawText("");
        setLastReviewItems([]);
      });
      setBanner({ type: "success", text: `已载入项目：${response.project_id}` });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "载入项目失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function chooseWorkspaceRoot() {
    setBusyLabel("正在切换工作空间");
    setBanner(null);
    try {
      const info = await window.qnuCopilot.chooseWorkspaceRoot();
      const projects = await window.qnuCopilot.listProjects();
      startTransition(() => {
        setAppInfo(info);
        setProjectList(projects.projects);
      });
      clearSelectedProjectState();
      setBanner({ type: "success", text: `工作空间已切换到：${info.workspaceRoot}` });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "切换工作空间失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function generateRecommendationPrompt() {
    if (!currentProject || !currentProject.state.project.need_reference_recommendation) {
      return;
    }
    setBusyLabel("正在生成推荐文献 Prompt");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.getReferenceRecommendationPrompt(
        currentProject.project_id,
      );
      startTransition(() => {
        setRecommendationPrompt(response);
      });
      setBanner({ type: "success", text: "推荐文献 Prompt 已生成，请发送给通用 LLM。" });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "生成推荐文献 Prompt 失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function importRecommendations() {
    if (!currentProject) {
      return;
    }
    if (!recommendationRawText.trim()) {
      setBanner({ type: "error", text: "请先粘贴推荐文献 JSON。" });
      return;
    }
    setBusyLabel("正在导入推荐文献 JSON");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.importRecommendations(
        currentProject.project_id,
        recommendationRawText,
      );
      syncCurrentProject(projectResponseFromState(response));
      await refreshProjectList();
      setBanner({
        type: "success",
        text: `已导入 ${response.imported_count} 篇推荐文献，中文 ${response.zh_count} / 英文 ${response.en_count}。`,
      });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "导入推荐文献失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function generateOutlinePrompt() {
    if (!currentProject) {
      return;
    }
    setBusyLabel("正在生成大纲 Prompt");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.getOutlinePrompt(currentProject.project_id);
      startTransition(() => {
        setOutlinePrompt(response);
      });
      setBanner({ type: "success", text: "大纲 Prompt 已生成，请发送给 NotebookLM。" });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "生成大纲 Prompt 失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function importOutline() {
    if (!currentProject) {
      return;
    }
    if (!outlineRawText.trim()) {
      setBanner({ type: "error", text: "请先粘贴大纲 JSON。" });
      return;
    }
    setBusyLabel("正在导入大纲 JSON");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.importOutline(
        currentProject.project_id,
        outlineRawText,
      );
      syncCurrentProject(projectResponseFromState(response));
      await refreshProjectList();
      setBanner({ type: "success", text: "大纲 JSON 已导入，可在下方继续调整后保存确认版。" });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "导入大纲失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function saveOutlineConfirmation() {
    if (!currentProject || !outlineDraft) {
      return;
    }
    setBusyLabel("正在保存确认版大纲");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.confirmOutline(
        currentProject.project_id,
        outlineDraft,
      );
      syncCurrentProject(response);
      await refreshProjectList();
      setBanner({ type: "success", text: "确认版大纲已保存，项目已进入切块规划阶段。" });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "保存确认版大纲失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function generateChunkPlanPrompt() {
    if (!currentProject?.state.outline.confirmed_tree) {
      return;
    }
    setBusyLabel("正在生成切块 Prompt");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.getChunkPlanPrompt(currentProject.project_id);
      startTransition(() => {
        setChunkPlanPrompt(response);
      });
      setBanner({ type: "success", text: "切块 Prompt 已生成，请发送给通用 LLM。" });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "生成切块 Prompt 失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function importChunkPlan() {
    if (!currentProject) {
      return;
    }
    if (!chunkPlanRawText.trim()) {
      setBanner({ type: "error", text: "请先粘贴切块规划 JSON。" });
      return;
    }
    setBusyLabel("正在导入切块规划 JSON");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.importChunkPlan(
        currentProject.project_id,
        chunkPlanRawText,
      );
      syncCurrentProject(projectResponseFromState(response));
      await refreshProjectList();
      setBanner({ type: "success", text: "切块规划 JSON 已导入，可在下方确认并保存。" });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "导入切块规划失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function saveChunkPlanConfirmation() {
    if (!currentProject || !chunkPlanDraft) {
      return;
    }
    setBusyLabel("正在保存确认版切块");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.confirmChunkPlan(
        currentProject.project_id,
        chunkPlanDraft,
      );
      syncCurrentProject(response);
      await refreshProjectList();
      setBanner({ type: "success", text: "确认版切块已保存，正文块工作台已启用。" });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "保存确认版切块失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function generateBlockPrompt() {
    if (!currentProject) {
      return;
    }
    const blockIndex = currentProject.state.generation.current_block_index;
    if (!blockIndex) {
      return;
    }
    setBusyLabel(`正在生成第 ${blockIndex} 块 Prompt`);
    setBanner(null);
    try {
      const response = await window.qnuCopilot.getBlockGenerationPrompt(
        currentProject.project_id,
        blockIndex,
      );
      startTransition(() => {
        setBlockPrompt(response);
      });
      setBanner({ type: "success", text: `第 ${blockIndex} 块正文 Prompt 已生成，请发送给 NotebookLM。` });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "生成正文块 Prompt 失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function importBlockContent() {
    if (!currentProject) {
      return;
    }
    const blockIndex = currentProject.state.generation.current_block_index;
    const currentTotalBlocks = currentProject.state.generation.total_blocks;
    if (!blockIndex) {
      return;
    }
    if (!blockRawText.trim()) {
      setBanner({ type: "error", text: "请先粘贴当前块的正文 JSON。" });
      return;
    }
    setBusyLabel(`正在导入第 ${blockIndex} 块正文`);
    setBanner(null);
    try {
      const response = await window.qnuCopilot.importBlockContent(
        currentProject.project_id,
        blockIndex,
        blockRawText,
      );
      syncCurrentProject(projectResponseFromState(response));
      await refreshProjectList();
      setBanner({
        type: "success",
        text:
          blockIndex === currentTotalBlocks
            ? `第 ${blockIndex} 块正文已导入，最后一块无需压缩。`
            : `第 ${blockIndex} 块正文已导入，请继续生成压缩上下文。`,
      });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "导入正文块失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function generateCompressPrompt() {
    if (!currentProject) {
      return;
    }
    const blockIndex = currentProject.state.generation.current_block_index;
    if (!blockIndex) {
      return;
    }
    setBusyLabel(`正在生成第 ${blockIndex} 块压缩 Prompt`);
    setBanner(null);
    try {
      const response = await window.qnuCopilot.getCompressPrompt(currentProject.project_id, blockIndex);
      startTransition(() => {
        setCompressPrompt(response);
      });
      setBanner({ type: "success", text: `第 ${blockIndex} 块压缩 Prompt 已生成，请发送给通用 LLM。` });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "生成压缩 Prompt 失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function importCompressedContext() {
    if (!currentProject) {
      return;
    }
    const blockIndex = currentProject.state.generation.current_block_index;
    if (!blockIndex) {
      return;
    }
    if (!compressRawText.trim()) {
      setBanner({ type: "error", text: "请先粘贴压缩上下文 JSON。" });
      return;
    }
    setBusyLabel(`正在导入第 ${blockIndex} 块压缩上下文`);
    setBanner(null);
    try {
      const response = await window.qnuCopilot.importCompressedContext(
        currentProject.project_id,
        blockIndex,
        compressRawText,
      );
      syncCurrentProject(projectResponseFromState(response));
      await refreshProjectList();
      setBanner({
        type: "success",
        text: `第 ${blockIndex} 块压缩上下文已导入，已推进到第 ${response.state.generation.current_block_index} 块。`,
      });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "导入压缩上下文失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function importSingleReference(sourceIndex: number) {
    if (!currentProject) {
      return;
    }
    const selected = await window.qnuCopilot.pickPdfFiles(false);
    if (!selected.length) {
      return;
    }
    setBusyLabel(`正在导入第 ${sourceIndex} 篇 PDF`);
    setBanner(null);
    try {
      await window.qnuCopilot.importReferencePdf(currentProject.project_id, sourceIndex, selected[0]);
      const refreshed = await window.qnuCopilot.getProject(currentProject.project_id);
      syncCurrentProject(refreshed);
      await refreshProjectList();
      setBanner({ type: "success", text: `第 ${sourceIndex} 篇文献的 PDF 已入库。` });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "导入 PDF 失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function skipReference(sourceIndex: number, reason: "unavailable" | "user_choice") {
    if (!currentProject) {
      return;
    }
    setBusyLabel(`正在更新第 ${sourceIndex} 篇文献状态`);
    setBanner(null);
    try {
      await window.qnuCopilot.skipReference(currentProject.project_id, sourceIndex, reason);
      const refreshed = await window.qnuCopilot.getProject(currentProject.project_id);
      syncCurrentProject(refreshed);
      await refreshProjectList();
      setBanner({
        type: "success",
        text: `第 ${sourceIndex} 篇文献已标记为${reason === "unavailable" ? "不可下载" : "主动跳过"}。`,
      });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "更新文献状态失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function batchImportPdfs() {
    if (!currentProject) {
      return;
    }
    const selected = await window.qnuCopilot.pickPdfFiles(true);
    if (!selected.length) {
      return;
    }
    setBusyLabel("正在批量处理 PDF");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.batchImportPdfs(currentProject.project_id, selected);
      syncCurrentProject(projectResponseFromState(response));
      startTransition(() => {
        setLastReviewItems(response.review_items);
      });
      await refreshProjectList();
      const reviewNote = response.review_items.length
        ? `，其中 ${response.review_items.length} 项待人工确认`
        : "";
      setBanner({
        type: "success",
        text: `已处理 ${response.processed_items.length} 个 PDF${reviewNote}。`,
      });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "批量导入失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function importBibtex() {
    if (!currentProject) {
      return;
    }
    if (!bibtexRawText.trim()) {
      setBanner({ type: "error", text: "请先粘贴 BibTeX 内容。" });
      return;
    }
    setBusyLabel("正在导入 BibTeX");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.importBibtex(currentProject.project_id, bibtexRawText);
      syncCurrentProject(projectResponseFromState(response));
      await refreshProjectList();
      setBanner({ type: "success", text: `已导入 ${response.imported_count} 条 BibTeX 记录。` });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "导入 BibTeX 失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  async function exportDocx() {
    if (!currentProject) {
      return;
    }
    setBusyLabel("正在导出论文文档");
    setBanner(null);
    try {
      const response = await window.qnuCopilot.exportDocx(
        currentProject.project_id,
        exportFilename.trim() || undefined,
      );
      syncCurrentProject(projectResponseFromState(response));
      startTransition(() => {
        setLastExportResult(response);
      });
      await refreshProjectList();
      setBanner({ type: "success", text: response.message });
    } catch (error) {
      setBanner({ type: "error", text: getErrorMessage(error, "导出论文失败。") });
    } finally {
      setBusyLabel("");
    }
  }

  function openInFolder(targetPath: string) {
    void window.qnuCopilot.showItemInFolder(targetPath);
  }

  const recommendedItems = currentProject?.state.references.recommended_items ?? [];
  const processedItems = currentProject?.state.references.processed_items ?? [];
  const bibtexEntries = currentProject?.state.references.bibtex_entries ?? [];
  const generationBlocks = currentProject?.state.generation.blocks ?? [];
  const currentBlockIndex = currentProject?.state.generation.current_block_index ?? 0;
  const totalBlocks = currentProject?.state.generation.total_blocks ?? 0;
  const activeBlock = findGenerationBlock(generationBlocks, currentBlockIndex);
  const lastDocxPath = currentProject?.state.export.last_docx_path ?? "";
  const lastExportedAt = currentProject?.state.export.last_exported_at ?? "";
  const importedCount = recommendedItems.filter((item) => item.status === "imported").length;
  const skippedCount = recommendedItems.filter((item) => item.status.startsWith("skipped")).length;
  const pendingCount = recommendedItems.filter((item) => item.status === "pending").length;
  const completedBlockCount = generationBlocks.filter((block) => block.normalized_json).length;
  const canImportOutline =
    !!currentProject &&
    processedItems.length >= currentProject.state.references.minimum_required;
  const hasConfirmedOutline = !!currentProject?.state.outline.confirmed_tree;
  const hasConfirmedChunkPlan = !!currentProject?.state.chunk_plan.confirmed_plan;
  const generationEnabled = hasConfirmedChunkPlan && generationBlocks.length > 0 && !!activeBlock;
  const compressionEnabled =
    !!activeBlock &&
    !!activeBlock.normalized_json &&
    activeBlock.block_index < totalBlocks &&
    !activeBlock.compressed_context_json;
  const allBlocksCompleted =
    generationBlocks.length > 0 && generationBlocks.every((block) => !!block.normalized_json);
  const exportReady = !!currentProject && allBlocksCompleted;
  const uiStep = getActiveUiStep(currentProject);
  const progress = getGlobalProgress(currentProject);
  const isWorking = currentProject !== null;

  return (
    <div className="app-shell">
      {/* 工作模式：顶部工作条 */}
      {isWorking && (
        <header className="workspace-header">
          <div className="workspace-header-left">
            <button 
              className="back-button"
              onClick={() => clearSelectedProjectState()}
              title="返回项目列表"
            >
              ← 返回
            </button>
            <div className="workspace-title">
              <h2>{currentProject?.state.project.title}</h2>
              <span className="project-id">ID: {currentProject?.project_id}</span>
            </div>
          </div>
          <div className="workspace-header-right">
            <div className="mini-progress">
              <strong>{progress.completed}/{progress.total}</strong>
              <div className="mini-progress-track">
                <div className="mini-progress-fill" style={{ width: `${progress.percent}%` }} />
              </div>
            </div>
            <button 
              className="ghost-button small"
              onClick={() => setShowStatusInfo(true)}
              title="查看工作区状态"
            >
              ℹ️ 状态
            </button>
            <button 
              className="api-settings-button floating-button"
              onClick={() => setShowAPISettings(true)}
              title="API 配置"
            >
              ⚙️
            </button>
          </div>
        </header>
      )}

      {/* 着陆模式：欢迎页面 */}
      {!isWorking && (
        <header className="hero">
          <div>
            <p className="eyebrow">QNU Thesis Copilot</p>
            <h1>半自动论文工作台</h1>
            <p className="hero-copy">
              当前桌面端已经接通本地 Python 内核，可完成项目初始化、推荐文献导入、PDF 规范化、
              BibTeX 管理，大纲确认，切块规划、逐块正文生成与压缩，以及最终 `.docx` 导出。
            </p>
          </div>
          <div className="status-cluster">
            <StatusPill
              label="Backend"
              value={backendStatus === "ready" ? "就绪" : backendStatus === "checking" ? "启动中" : "异常"}
              tone={backendStatus === "ready" ? "success" : backendStatus === "checking" ? "info" : "error"}
            />
            <StatusPill label="状态" value={busyLabel || "就绪"} tone={busyLabel ? "info" : "neutral"} />
          </div>
        </header>
      )}
      
      {/* 工作模式：隐藏顶部浮动按钮，移到header */}
      {!isWorking && (
        <button 
          className="api-settings-button floating-button"
          onClick={() => setShowAPISettings(true)}
          title="API 配置"
        >
          ⚙️
        </button>
      )}
      
      {/* API 配置 Modal */}
      {showAPISettings && (
        <div className="modal-overlay" onClick={() => setShowAPISettings(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <APISettingsPanel onClose={() => setShowAPISettings(false)} />
          </div>
        </div>
      )}

      {/* 状态信息抽屉（仅在工作模式显示） */}
      {isWorking && showStatusInfo && (
        <div className="status-drawer-overlay" onClick={() => setShowStatusInfo(false)}>
          <div className="status-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <h3>工作区状态</h3>
              <button 
                className="close-button"
                onClick={() => setShowStatusInfo(false)}
              >
                ✕
              </button>
            </div>
            <div className="drawer-content">
              <div className="status-grid">
                <div className="status-item">
                  <span className="status-label">项目 ID</span>
                  <strong>{currentProject?.project_id}</strong>
                </div>
                <div className="status-item">
                  <span className="status-label">项目路径</span>
                  <code>{currentProject?.project_root}</code>
                </div>
                <div className="status-item">
                  <span className="status-label">状态文件</span>
                  <code>{currentProject?.state_path}</code>
                </div>
                <div className="status-item">
                  <span className="status-label">工作区</span>
                  <strong>{appInfo?.workspaceRoot ?? "未初始化"}</strong>
                </div>
                <div className="status-item">
                  <span className="status-label">数据目录</span>
                  <code>{appInfo?.dataRoot ?? "未初始化"}</code>
                </div>
                <div className="status-item">
                  <span className="status-label">后端 URL</span>
                  <code>{appInfo?.backendUrl ?? "未初始化"}</code>
                </div>
                <div className="status-item">
                  <span className="status-label">Backend 状态</span>
                  <strong className={`status-value-${backendStatus}`}>
                    {backendStatus === "ready" ? "就绪" : backendStatus === "checking" ? "启动中" : "异常"}
                  </strong>
                </div>
              </div>
              <div className="drawer-actions">
                <button 
                  className="secondary-button"
                  onClick={() => currentProject && openInFolder(currentProject.project_root)}
                >
                  打开项目目录
                </button>
                <button 
                  className="ghost-button"
                  onClick={() => appInfo && openInFolder(appInfo.dataRoot)}
                >
                  打开数据目录
                </button>
                <button 
                  className="ghost-button"
                  onClick={() => void chooseWorkspaceRoot()}
                >
                  切换工作空间
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 通知 Banner */}
      {banner ? <div className={`banner banner-${banner.type}`}>{banner.text}</div> : null}

      {/* ============ 着陆页面 ============ */}
      {!isWorking && (
      <main className="landing-layout">
        <section className="card primary-card">
          <div className="section-head">
            <div>
              <p className="section-kicker">Step 1</p>
              <h2>新建或载入项目</h2>
            </div>
            {appInfo ? (
              <button className="ghost-button" onClick={() => openInFolder(appInfo.dataRoot)}>
                打开本地数据目录
              </button>
            ) : null}
          </div>

          <div className="grid-two">
            <label>
              论文题目
              <input
                value={projectForm.title}
                onChange={(event) =>
                  setProjectForm((current) => ({ ...current, title: event.target.value }))
                }
                placeholder="例如：基于 XXX 的物联网水质检测系统"
              />
            </label>
            <label>
              最低文献数
              <input
                type="number"
                min={1}
                value={projectForm.minimumRequiredReferences}
                onChange={(event) =>
                  setProjectForm((current) => ({
                    ...current,
                    minimumRequiredReferences: Number(event.target.value || 1),
                  }))
                }
              />
            </label>
          </div>

          <label>
            核心思想
            <textarea
              rows={6}
              value={projectForm.coreIdea}
              onChange={(event) =>
                setProjectForm((current) => ({ ...current, coreIdea: event.target.value }))
              }
              placeholder="用 200-300 字写清项目要解决的问题、核心方法和预期贡献。"
            />
          </label>

          <div className="grid-two">
            <label>
              最低总字数（可选）
              <input
                type="number"
                min={0}
                value={projectForm.minimumTotalWords}
                onChange={(event) =>
                  setProjectForm((current) => ({
                    ...current,
                    minimumTotalWords: event.target.value,
                  }))
                }
                placeholder="例如 12000"
              />
            </label>
            <label className="toggle">
              <span>需要系统推荐参考文献</span>
              <input
                type="checkbox"
                checked={projectForm.needReferenceRecommendation}
                onChange={(event) =>
                  setProjectForm((current) => ({
                    ...current,
                    needReferenceRecommendation: event.target.checked,
                  }))
                }
              />
            </label>
          </div>

          <div className="action-row">
            <button className="primary-button" onClick={() => void createProject()}>
              创建新项目
            </button>
            <div className="inline-loader">
              <input
                value={projectIdInput}
                onChange={(event) => setProjectIdInput(event.target.value)}
                placeholder="输入已有项目 ID"
              />
              <button className="secondary-button" onClick={() => void loadProject()}>
                载入已有项目
              </button>
            </div>
          </div>
        </section>

        <aside className="card side-card">
          <div className="section-head">
            <div>
              <p className="section-kicker">Workspace</p>
              <h2>运行环境</h2>
            </div>
          </div>
          <dl className="meta-list">
            <div>
              <dt>桌面模式</dt>
              <dd>{appInfo?.isDev ? "开发态" : "运行态"}</dd>
            </div>
            <div>
              <dt>工作空间</dt>
              <dd>{appInfo?.workspaceRoot ?? "等待后端启动"}</dd>
            </div>
            <div>
              <dt>数据目录</dt>
              <dd>{appInfo?.dataRoot ?? "等待后端启动"}</dd>
            </div>
            <div>
              <dt>Backend URL</dt>
              <dd>{appInfo?.backendUrl ?? "等待后端启动"}</dd>
            </div>
            <div>
              <dt>当前项目</dt>
              <dd>{currentProject?.project_id ?? "尚未载入"}</dd>
            </div>
          </dl>
          <p className="note">
            现在已经支持首次选择工作空间和后续切换。后端会始终挂在当前工作空间之上。
          </p>
        </aside>

        <ProjectListPanel
          projects={projectList}
          currentProjectId={currentProject?.project_id}
          onLoadProject={(projectId) => {
            void loadProjectById(projectId);
          }}
          onRefresh={() => {
            void refreshProjectList();
          }}
          onChooseWorkspace={() => {
            void chooseWorkspaceRoot();
          }}
        />

        <section className="card">
          <div className="section-head">
            <div>
              <p className="section-kicker">Step 2</p>
              <h2>项目状态</h2>
            </div>
            {currentProject ? (
              <div className="mini-actions">
                <button className="ghost-button" onClick={() => openInFolder(currentProject.project_root)}>
                  打开项目目录
                </button>
                <button className="ghost-button" onClick={() => openInFolder(currentProject.state_path)}>
                  打开 state.json
                </button>
              </div>
            ) : null}
          </div>

          {currentProject ? (
            <div className="project-summary">
              <div className="summary-block">
                <span>题目</span>
                <strong>{currentProject.state.project.title}</strong>
              </div>
              <div className="summary-block">
                <span>引用流程</span>
                <strong>
                  {currentProject.state.project.need_reference_recommendation
                    ? "推荐文献路线"
                    : "已有 PDF 路线"}
                </strong>
              </div>
              <div className="summary-block">
                <span>已入库 PDF</span>
                <strong>
                  {processedItems.length} / {currentProject.state.references.minimum_required}
                </strong>
              </div>
              <div className="summary-block">
                <span>推荐文献状态</span>
                <strong>
                  已导入 {importedCount}，已跳过 {skippedCount}，待处理 {pendingCount}
                </strong>
              </div>
              <div className="summary-block">
                <span>大纲状态</span>
                <strong>{outlineStatusLabel(currentProject)}</strong>
              </div>
              <div className="summary-block">
                <span>BibTeX 条目</span>
                <strong>{bibtexEntries.length}</strong>
              </div>
              <div className="summary-block">
                <span>正文块进度</span>
                <strong>
                  {completedBlockCount} / {totalBlocks || 0}
                  {currentBlockIndex ? `，当前块 ${currentBlockIndex}` : ""}
                </strong>
              </div>
              <div className="summary-block">
                <span>最近导出</span>
                <strong>{lastExportedAt ? formatTimestamp(lastExportedAt) : "尚未导出"}</strong>
              </div>
            </div>
          ) : (
            <p className="empty-state">先创建或载入项目，这里会显示当前状态和关键路径。</p>
          )}
        </section>

        {uiStep === "recommendation" ? (
        <section className="card">
          <div className="section-head">
            <div>
              <p className="section-kicker">Step 3</p>
              <h2>推荐文献 JSON 导入</h2>
            </div>
            <div className="mini-actions">
              <button
                className="ghost-button"
                disabled={!currentProject || !currentProject.state.project.need_reference_recommendation}
                onClick={() => void generateRecommendationPrompt()}
              >
                生成推荐 Prompt
              </button>
            </div>
          </div>
          <p className="note">
            {currentProject?.state.project.need_reference_recommendation
              ? "先生成推荐 Prompt 发给通用 LLM，再把外部 AI 返回的严格 JSON 整段粘贴进来。"
              : "当前项目走“已有 PDF 路线”，这一段可直接跳过。"}
          </p>
          <PromptPreviewCard preview={recommendationPrompt} onOpenSnapshot={openInFolder} />
          <textarea
            rows={10}
            value={recommendationRawText}
            onChange={(event) => setRecommendationRawText(event.target.value)}
            placeholder="在这里粘贴推荐文献 JSON..."
            disabled={!currentProject || !currentProject.state.project.need_reference_recommendation}
          />
          <div className="action-row">
            <button
              className="primary-button"
              disabled={!currentProject || !currentProject.state.project.need_reference_recommendation}
              onClick={() => void importRecommendations()}
            >
              导入推荐 JSON
            </button>
          </div>
        </section>
        ) : null}

        {uiStep === "pdf" ? (
        <section className="card wide-card">
          <div className="section-head">
            <div>
              <p className="section-kicker">Step 4</p>
              <h2>PDF 资产处理</h2>
            </div>
            <button
              className="secondary-button"
              disabled={!currentProject}
              onClick={() => void batchImportPdfs()}
            >
              批量选择 PDF
            </button>
          </div>

          {currentProject?.state.project.need_reference_recommendation ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>标题</th>
                    <th>语言</th>
                    <th>状态</th>
                    <th>下载链接</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {recommendedItems.map((item) => (
                    <tr key={item.source_index}>
                      <td>{item.source_index}</td>
                      <td>
                        <strong>{item.title}</strong>
                        <div className="subtle-line">
                          {item.venue ?? "未提供来源"} {item.year ? `· ${item.year}` : ""}
                        </div>
                      </td>
                      <td>{item.language}</td>
                      <td>
                        <span className={`badge badge-${referenceStatusTone(item.status)}`}>
                          {referenceStatusLabel(item.status)}
                        </span>
                      </td>
                      <td>
                        <a href={item.download_url} target="_blank" rel="noreferrer">
                          打开链接
                        </a>
                      </td>
                      <td>
                        <div className="mini-actions">
                          <button
                            className="ghost-button"
                            disabled={item.status !== "pending"}
                            onClick={() => void importSingleReference(item.source_index)}
                          >
                            导入 PDF
                          </button>
                          <button
                            className="ghost-button"
                            disabled={item.status !== "pending"}
                            onClick={() => void skipReference(item.source_index, "unavailable")}
                          >
                            不可下载
                          </button>
                          <button
                            className="ghost-button"
                            disabled={item.status !== "pending"}
                            onClick={() => void skipReference(item.source_index, "user_choice")}
                          >
                            主动跳过
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="manual-panel">
              <p>
                当前项目走“已有 PDF 路线”。请点击上方“批量选择 PDF”，一次导入已经按论文标题命名的文件，
                系统会自动完成连续编号和规范化复制。
              </p>
            </div>
          )}

          {lastReviewItems.length ? (
            <div className="review-box">
              <h3>待人工确认</h3>
              <ul>
                {lastReviewItems.map((item) => (
                  <li key={item.file_path}>
                    <code>{item.file_path}</code>：{item.reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
        ) : null}

        {uiStep === "bibtex" ? (
        <section className="card wide-card">
          <div className="section-head">
            <div>
              <p className="section-kicker">Step 5</p>
              <h2>BibTeX 导入与检查</h2>
            </div>
            <div className="mini-actions">
              <button
                className="primary-button"
                disabled={!currentProject}
                onClick={() => {
                  void importBibtex();
                }}
              >
                导入 BibTeX
              </button>
            </div>
          </div>

          <p className="note">
            推荐文献路线下，这里会自动带出从推荐 JSON 中提取到的 BibTeX；你也可以手动覆盖为更完整的版本。
            已有 PDF 路线下，请务必在这里粘贴对应文献的 BibTeX，导出时会优先按这里的内容生成参考文献。
          </p>

          <div className="project-summary">
            <div className="summary-block">
              <span>当前条目数</span>
              <strong>{bibtexEntries.length}</strong>
            </div>
            <div className="summary-block">
              <span>建议状态</span>
              <strong>{bibtexEntries.length ? "可继续后续流程" : "建议先导入再继续"}</strong>
            </div>
          </div>

          <textarea
            rows={10}
            value={bibtexRawText}
            onChange={(event) => setBibtexRawText(event.target.value)}
            placeholder="在这里粘贴 BibTeX 内容..."
            disabled={!currentProject}
          />
        </section>
        ) : null}

        {uiStep === "outline" ? (
        <OutlineTreeEditor
          tree={outlineDraft}
          promptPreview={outlinePrompt}
          onChange={setOutlineDraft}
          onSave={() => {
            void saveOutlineConfirmation();
          }}
          onGeneratePrompt={() => {
            void generateOutlinePrompt();
          }}
          onImport={() => {
            void importOutline();
          }}
          onOpenSnapshot={openInFolder}
          importDisabled={!canImportOutline || hasConfirmedChunkPlan}
          generatePromptDisabled={!canImportOutline || hasConfirmedChunkPlan}
          saveDisabled={!outlineDraft || hasConfirmedChunkPlan}
          editingDisabled={hasConfirmedChunkPlan}
          rawText={outlineRawText}
          onRawTextChange={setOutlineRawText}
        />
        ) : null}

        {uiStep === "chunk" ? (
        <ChunkPlanEditor
          plan={chunkPlanDraft}
          promptPreview={chunkPlanPrompt}
          rawText={chunkPlanRawText}
          importDisabled={!hasConfirmedOutline}
          saveDisabled={!chunkPlanDraft}
          onRawTextChange={setChunkPlanRawText}
          onPlanChange={setChunkPlanDraft}
          onGeneratePrompt={() => {
            void generateChunkPlanPrompt();
          }}
          onImport={() => {
            void importChunkPlan();
          }}
          onSave={() => {
            void saveChunkPlanConfirmation();
          }}
          onOpenSnapshot={openInFolder}
        />
        ) : null}

        {uiStep === "generation" ? (
        <GenerationWorkbench
          blocks={generationBlocks}
          currentBlockIndex={currentBlockIndex}
          totalBlocks={totalBlocks}
          generationPrompt={blockPrompt}
          compressPrompt={compressPrompt}
          blockRawText={blockRawText}
          compressRawText={compressRawText}
          generateBlockDisabled={!generationEnabled || !!activeBlock?.normalized_json}
          importBlockDisabled={!generationEnabled || !!activeBlock?.normalized_json || !blockRawText.trim()}
          generateCompressDisabled={!compressionEnabled}
          importCompressDisabled={!compressionEnabled || !compressRawText.trim()}
          blockInputDisabled={!generationEnabled || !!activeBlock?.normalized_json}
          compressInputDisabled={!compressionEnabled}
          onBlockRawTextChange={setBlockRawText}
          onCompressRawTextChange={setCompressRawText}
          onGenerateBlockPrompt={() => {
            void generateBlockPrompt();
          }}
          onImportBlock={() => {
            void importBlockContent();
          }}
          onGenerateCompressPrompt={() => {
            void generateCompressPrompt();
          }}
          onImportCompress={() => {
            void importCompressedContext();
          }}
          onOpenSnapshot={openInFolder}
        />
        ) : null}

        {uiStep === "export" || uiStep === "done" ? (
        <section className="card wide-card">
          <div className="section-head">
            <div>
              <p className="section-kicker">Step 9</p>
              <h2>最终导出</h2>
            </div>
            <div className="mini-actions">
              {lastDocxPath ? (
                <button className="ghost-button" onClick={() => openInFolder(lastDocxPath)}>
                  打开最近导出
                </button>
              ) : null}
              <button
                className="primary-button"
                disabled={!exportReady}
                onClick={() => {
                  void exportDocx();
                }}
              >
                导出 DOCX
              </button>
            </div>
          </div>

          {allBlocksCompleted && (
            <AIGCPanel blocks={generationBlocks} />
          )}

          <p className="note">
            当全部正文块都已导入后，这里会解锁导出。系统会在本地完成引用占位符还原、参考文献整理并生成
            `.docx` 文件；若仓库内存在学校模板文件，后续可直接切换为模板注入模式。
          </p>

          <div className="grid-two">
            <label>
              导出文件名（可选）
              <input
                value={exportFilename}
                onChange={(event) => setExportFilename(event.target.value)}
                placeholder="默认使用论文题目"
                disabled={!currentProject}
              />
            </label>
            <div className="summary-block">
              <span>导出条件</span>
              <strong>{exportReady ? "已满足，可导出" : "请先完成全部正文块"}</strong>
              <p className="note">
                正文完成 {completedBlockCount} / {totalBlocks || 0}，BibTeX {bibtexEntries.length} 条
              </p>
            </div>
          </div>

          {lastExportResult?.export_history && lastExportResult.export_history.length > 0 ? (
            <div className="export-history">
              <h3>导出历史</h3>
              <div className="export-history-list">
                {lastExportResult.export_history.map((item: ExportHistoryItem, index: number) => (
                  <div key={index} className="export-history-item">
                    <div className="export-history-info">
                      <strong>{index + 1}. {formatTimestamp(item.exported_at)}</strong>
                      <span>参考文献 {item.reference_count} 篇</span>
                    </div>
                    <div className="mini-actions">
                      <button className="ghost-button" onClick={() => openInFolder(item.output_path)}>
                        打开文件
                      </button>
                      <button className="ghost-button" onClick={() => openInFolder(item.log_path)}>
                        查看日志
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : lastExportResult || lastDocxPath ? (
            <div className="export-result">
              <div className="summary-block">
                <span>最近输出文件</span>
                <strong>{lastExportResult?.output_path ?? lastDocxPath}</strong>
              </div>
              <div className="summary-block">
                <span>导出日志</span>
                <strong>{lastExportResult?.log_path ?? guessExportLogPath(lastDocxPath)}</strong>
              </div>
            </div>
          ) : (
            <p className="empty-state">导出完成后，这里会显示文档路径和日志路径。</p>
          )}
        </section>
        ) : null}

        {uiStep === "pdf" || uiStep === "done" ? (
        <section className="card">
          <div className="section-head">
            <div>
              <p className="section-kicker">Processed PDFs</p>
              <h2>已入库 PDF</h2>
            </div>
          </div>
          {processedItems.length ? (
            <ul className="processed-list">
              {processedItems.map((item) => (
                <li key={`${item.effective_index}-${item.sha256}`}>
                  <div>
                    <strong>
                      {String(item.effective_index).padStart(2, "0")} · {item.title}
                    </strong>
                    <p>{item.processed_pdf_path}</p>
                  </div>
                  <button className="ghost-button" onClick={() => openInFolder(item.processed_pdf_path)}>
                    打开位置
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-state">还没有入库的 PDF。</p>
          )}
        </section>
        ) : null}
      </main>
    </div>
  );
}

function projectResponseFromState<T extends ProjectStateResponse>(response: T): ProjectStateResponse {
  return {
    project_id: response.project_id,
    project_root: response.project_root,
    state_path: response.state_path,
    workflow_stage: response.workflow_stage,
    state: response.state,
  };
}

function findGenerationBlock(blocks: GeneratedBlockState[], blockIndex: number) {
  return blocks.find((block) => block.block_index === blockIndex) ?? null;
}

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

function referenceStatusTone(status: string) {
  if (status === "imported") {
    return "success";
  }
  if (status.startsWith("skipped")) {
    return "warning";
  }
  return "neutral";
}

function referenceStatusLabel(status: string) {
  if (status === "imported") {
    return "已导入";
  }
  if (status === "skipped_unavailable") {
    return "不可下载";
  }
  if (status === "skipped_user_choice") {
    return "主动跳过";
  }
  if (status === "match_failed") {
    return "匹配失败";
  }
  return "待处理";
}

function workflowStageLabel(stage?: string) {
  const labels: Record<string, string> = {
    references: "文献准备",
    pdf_processing: "PDF 处理",
    outline_generation: "大纲生成",
    outline_editing: "大纲确认",
    chunk_planning: "切块规划",
    block_generation: "正文生成",
    export: "导出阶段",
    done: "已完成",
  };
  return stage ? labels[stage] ?? stage : "未创建项目";
}

function getActiveUiStep(project: ProjectStateResponse | null): UiStep {
  if (!project) {
    return "project";
  }

  const needRecommendation = project.state.project.need_reference_recommendation;
  const hasRecommendations = project.state.references.recommended_items.length > 0;
  if (needRecommendation && !hasRecommendations) {
    return "recommendation";
  }

  const minimumRequired = project.state.references.minimum_required;
  const processedCount = project.state.references.processed_items.length;
  if (processedCount < minimumRequired) {
    return "pdf";
  }

  const bibtexCount = project.state.references.bibtex_entries.length;
  if (bibtexCount < 1) {
    return "bibtex";
  }

  if (!project.state.outline.confirmed_tree) {
    return "outline";
  }

  if (!project.state.chunk_plan.confirmed_plan) {
    return "chunk";
  }

  const blocks = project.state.generation.blocks;
  const allBlocksCompleted = blocks.length > 0 && blocks.every((block) => !!block.normalized_json);
  if (!allBlocksCompleted) {
    return "generation";
  }

  if (project.workflow_stage === "done" || !!project.state.export.last_docx_path) {
    return "done";
  }

  return "export";
}

function getGlobalProgress(project: ProjectStateResponse | null) {
  const total = 7;
  if (!project) {
    return { completed: 0, total, percent: 0 };
  }

  const checklist = [
    !project.state.project.need_reference_recommendation ||
      project.state.references.recommended_items.length > 0,
    project.state.references.processed_items.length >= project.state.references.minimum_required,
    project.state.references.bibtex_entries.length > 0,
    !!project.state.outline.confirmed_tree,
    !!project.state.chunk_plan.confirmed_plan,
    project.state.generation.blocks.length > 0 &&
      project.state.generation.blocks.every((block) => !!block.normalized_json),
    !!project.state.export.last_docx_path || project.workflow_stage === "done",
  ];

  const completed = checklist.filter(Boolean).length;
  return {
    completed,
    total,
    percent: Math.round((completed / total) * 100),
  };
}

function uiStepLabel(step: UiStep) {
  const labels: Record<UiStep, string> = {
    project: "新建或载入项目",
    recommendation: "导入推荐文献 JSON",
    pdf: "PDF 资产处理",
    bibtex: "导入 BibTeX",
    outline: "大纲导入与确认",
    chunk: "切块规划",
    generation: "正文逐块生成",
    export: "最终导出",
    done: "流程已完成",
  };
  return labels[step];
}

function outlineStatusLabel(project: ProjectStateResponse) {
  if (project.state.outline.confirmed_tree) {
    return "已确认";
  }
  if (project.state.outline.normalized_json) {
    return "已导入待确认";
  }
  return "未开始";
}

function joinBibtexEntries(project: ProjectStateResponse) {
  return project.state.references.bibtex_entries.map((entry) => entry.raw_text).join("\n\n");
}

function guessExportLogPath(docxPath: string) {
  if (!docxPath) {
    return "";
  }
  return docxPath.replace(/\.docx$/i, ".export.json");
}

function formatTimestamp(value: string) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function StatusPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "success" | "error" | "info" | "neutral";
}) {
  return (
    <div className={`status-pill status-pill-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default App;

const { contextBridge, ipcRenderer } = require("electron");

const BACKEND_URL = "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const hasBody = options.body !== undefined && options.body !== null;
  const headers = {
    ...(options.headers || {}),
  };
  if (hasBody && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${BACKEND_URL}${path}`, {
    ...options,
    method,
    headers,
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    payload = null;
  }

  if (!response.ok) {
    const message =
      payload && typeof payload.message === "string"
        ? payload.message
        : `Request failed with status ${response.status}`;
    const error = new Error(message);
    error.details = payload && payload.details ? payload.details : {};
    error.status = response.status;
    throw error;
  }

  return payload;
}

contextBridge.exposeInMainWorld("qnuCopilot", {
  getConfig: () => request("/config", { method: "GET" }),
  updateProvider: (providerId, payload) =>
    request(`/config/providers/${providerId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  updateNotebookLM: (payload) =>
    request("/config/notebooklm", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  setDefaultProvider: (payload) =>
    request("/config/default", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  getProviderStatus: (providerId) => request(`/config/providers/${providerId}/status`, { method: "GET" }),
  listProviderStatus: () => request("/config/providers", { method: "GET" }),
  getAppInfo: () => ipcRenderer.invoke("app:get-info"),
  health: () => request("/health", { method: "GET" }),
  listProjects: () => request("/projects", { method: "GET" }),
  createProject: (payload) =>
    request("/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getProject: (projectId) => request(`/projects/${projectId}`, { method: "GET" }),
  getReferenceRecommendationPrompt: (projectId) =>
    request(`/projects/${projectId}/prompts/references/recommendation`, {
      method: "GET",
    }),
  getOutlinePrompt: (projectId) =>
    request(`/projects/${projectId}/prompts/outline`, {
      method: "GET",
    }),
  importRecommendations: (projectId, rawText) =>
    request(`/projects/${projectId}/references/recommendations/import`, {
      method: "POST",
      body: JSON.stringify({ raw_text: rawText }),
    }),
  importOutline: (projectId, rawText) =>
    request(`/projects/${projectId}/outline/import`, {
      method: "POST",
      body: JSON.stringify({ raw_text: rawText }),
    }),
  confirmOutline: (projectId, outlineTree) =>
    request(`/projects/${projectId}/outline/confirmed`, {
      method: "PUT",
      body: JSON.stringify({ outline_tree: outlineTree }),
    }),
  getChunkPlanPrompt: (projectId) =>
    request(`/projects/${projectId}/prompts/chunk-plan`, {
      method: "GET",
    }),
  importChunkPlan: (projectId, rawText) =>
    request(`/projects/${projectId}/chunk-plan/import`, {
      method: "POST",
      body: JSON.stringify({ raw_text: rawText }),
    }),
  confirmChunkPlan: (projectId, chunkPlan) =>
    request(`/projects/${projectId}/chunk-plan/confirmed`, {
      method: "PUT",
      body: JSON.stringify({ chunk_plan: chunkPlan }),
    }),
  getBlockGenerationPrompt: (projectId, blockIndex) =>
    request(`/projects/${projectId}/prompts/blocks/${blockIndex}/generate`, {
      method: "GET",
    }),
  getCompressPrompt: (projectId, blockIndex) =>
    request(`/projects/${projectId}/prompts/blocks/${blockIndex}/compress`, {
      method: "GET",
    }),
  importBlockContent: (projectId, blockIndex, rawText) =>
    request(`/projects/${projectId}/blocks/${blockIndex}/import`, {
      method: "POST",
      body: JSON.stringify({ raw_text: rawText }),
    }),
  importCompressedContext: (projectId, blockIndex, rawText) =>
    request(`/projects/${projectId}/blocks/${blockIndex}/compressed-context/import`, {
      method: "POST",
      body: JSON.stringify({ raw_text: rawText }),
    }),
  skipReference: (projectId, sourceIndex, reason) =>
    request(`/projects/${projectId}/references/${sourceIndex}/skip`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  importReferencePdf: (projectId, sourceIndex, pdfPath) =>
    request(`/projects/${projectId}/references/${sourceIndex}/pdf`, {
      method: "POST",
      body: JSON.stringify({ pdf_path: pdfPath }),
    }),
  importBibtex: (projectId, rawText) =>
    request(`/projects/${projectId}/references/bibtex/import`, {
      method: "POST",
      body: JSON.stringify({ raw_text: rawText }),
    }),
  batchImportPdfs: (projectId, pdfPaths) =>
    request(`/projects/${projectId}/references/pdfs/batch`, {
      method: "POST",
      body: JSON.stringify({ pdf_paths: pdfPaths }),
    }),
  exportDocx: (projectId, outputFilename) =>
    request(`/projects/${projectId}/export/docx`, {
      method: "POST",
      body: JSON.stringify({ output_filename: outputFilename || null }),
    }),
  parseContract: (contractType, rawText, projectId) =>
    request(`/contracts/${contractType}/parse`, {
      method: "POST",
      body: JSON.stringify({ raw_text: rawText, project_id: projectId || null }),
    }),
  pickPdfFiles: (multiple = false) => ipcRenderer.invoke("dialog:pick-pdf-files", multiple),
  showItemInFolder: (targetPath) => ipcRenderer.invoke("shell:show-item-in-folder", targetPath),
  chooseWorkspaceRoot: () => ipcRenderer.invoke("workspace:choose-root"),
  setLastProjectId: (projectId) => ipcRenderer.invoke("app:set-last-project", projectId),
});

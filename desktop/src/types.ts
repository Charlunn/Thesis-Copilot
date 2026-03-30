export type JsonRecord = Record<string, unknown>;

export interface QnuCopilotApi {
  // API Configuration
  getConfig: () => Promise<APIConfig>;
  updateProvider: (providerId: string, update: UpdateProviderRequest) => Promise<APIConfig>;
  updateNotebookLM: (update: UpdateNotebookLMRequest) => Promise<APIConfig>;
  setDefaultProvider: (request: SetDefaultProviderRequest) => Promise<APIConfig>;
  getProviderStatus: (providerId: string) => Promise<ProviderStatus>;
  listProviderStatus: () => Promise<ProviderStatus[]>;
  
  getAppInfo: () => Promise<{
    ready: boolean;
    dataRoot: string;
    workspaceRoot: string;
    lastProjectId: string;
    backendUrl: string;
    isDev: boolean;
  }>;
  health: () => Promise<{ status: string }>;
  listProjects: () => Promise<ProjectListResponse>;
  createProject: (payload: JsonRecord) => Promise<ProjectStateResponse>;
  getProject: (projectId: string) => Promise<ProjectStateResponse>;
  importRecommendations: (
    projectId: string,
    rawText: string,
  ) => Promise<RecommendationImportResult>;
  getReferenceRecommendationPrompt: (projectId: string) => Promise<PromptPreviewResponse>;
  getOutlinePrompt: (projectId: string) => Promise<PromptPreviewResponse>;
  importOutline: (projectId: string, rawText: string) => Promise<OutlineImportResult>;
  confirmOutline: (
    projectId: string,
    outlineTree: ConfirmedOutlineTree,
  ) => Promise<ProjectStateResponse>;
  getChunkPlanPrompt: (projectId: string) => Promise<PromptPreviewResponse>;
  importChunkPlan: (projectId: string, rawText: string) => Promise<ChunkPlanImportResult>;
  confirmChunkPlan: (
    projectId: string,
    chunkPlan: ChunkPlan,
  ) => Promise<ProjectStateResponse>;
  getBlockGenerationPrompt: (
    projectId: string,
    blockIndex: number,
  ) => Promise<PromptPreviewResponse>;
  getCompressPrompt: (
    projectId: string,
    blockIndex: number,
  ) => Promise<PromptPreviewResponse>;
  importBlockContent: (
    projectId: string,
    blockIndex: number,
    rawText: string,
  ) => Promise<BlockImportResult>;
  importCompressedContext: (
    projectId: string,
    blockIndex: number,
    rawText: string,
  ) => Promise<BlockImportResult>;
  skipReference: (
    projectId: string,
    sourceIndex: number,
    reason: "unavailable" | "user_choice",
  ) => Promise<SkipReferenceResponse>;
  importReferencePdf: (
    projectId: string,
    sourceIndex: number,
    pdfPath: string,
  ) => Promise<ProcessedReferenceResponse>;
  importBibtex: (
    projectId: string,
    rawText: string,
  ) => Promise<BibtexImportResult>;
  batchImportPdfs: (
    projectId: string,
    pdfPaths: string[],
  ) => Promise<BatchImportResult>;
  exportDocx: (
    projectId: string,
    outputFilename?: string,
  ) => Promise<ExportProjectResult>;
  parseContract: (
    contractType: string,
    rawText: string,
    projectId?: string,
  ) => Promise<JsonRecord>;
  pickPdfFiles: (multiple?: boolean) => Promise<string[]>;
  showItemInFolder: (targetPath: string) => Promise<boolean>;
  chooseWorkspaceRoot: () => Promise<{
    ready: boolean;
    dataRoot: string;
    workspaceRoot: string;
    lastProjectId: string;
    backendUrl: string;
    isDev: boolean;
  }>;
  setLastProjectId: (projectId: string) => Promise<boolean>;
}

export interface ProjectInfo {
  title: string;
  core_idea: string;
  need_reference_recommendation: boolean;
  minimum_total_words?: number | null;
}

export interface RecommendedReferenceItem {
  source_index: number;
  title: string;
  language: string;
  download_url: string;
  venue?: string | null;
  year?: number | null;
  impact_note?: string | null;
  bibtex_key?: string | null;
  status: string;
}

export interface ProcessedReferenceItem {
  effective_index: number;
  source_index?: number | null;
  title: string;
  normalized_title: string;
  language?: string | null;
  raw_pdf_path: string;
  processed_pdf_path: string;
  file_size: number;
  sha256: string;
  bibtex_key?: string | null;
}

export interface BibtexEntry {
  key?: string | null;
  raw_text: string;
  title?: string | null;
}

export interface ProjectState {
  project_id: string;
  workflow_stage: string;
  project: ProjectInfo;
  references: {
    recommended_items: RecommendedReferenceItem[];
    processed_items: ProcessedReferenceItem[];
    bibtex_entries: BibtexEntry[];
    minimum_required: number;
  };
  outline: {
    raw_ai_text: string;
    normalized_json?: OutlineTree | null;
    confirmed_tree?: ConfirmedOutlineTree | null;
    status: string;
  };
  chunk_plan: {
    raw_ai_text: string;
    normalized_json?: ChunkPlan | null;
    confirmed_plan?: ChunkPlan | null;
    status: string;
  };
  generation: {
    current_block_index: number;
    total_blocks: number;
    latest_compressed_context?: CompressedContextPayload | null;
    status: string;
    blocks: GeneratedBlockState[];
  };
  export: {
    last_docx_path: string;
    last_exported_at: string;
    status: string;
  };
}

export interface ProjectStateResponse {
  project_id: string;
  project_root: string;
  state_path: string;
  workflow_stage: string;
  state: ProjectState;
}

export interface RecommendationImportResult extends ProjectStateResponse {
  imported_count: number;
  zh_count: number;
  en_count: number;
  parse_result: {
    warnings: string[];
    raw_snapshot_path?: string | null;
    normalized_snapshot_path?: string | null;
  };
}

export interface SkipReferenceResponse {
  workflow_stage: string;
  item: RecommendedReferenceItem;
}

export interface ProcessedReferenceResponse {
  workflow_stage: string;
  item: ProcessedReferenceItem;
}

export interface BatchImportResult extends ProjectStateResponse {
  processed_items: ProcessedReferenceItem[];
  review_items: { file_path: string; reason: string }[];
}

export interface BibtexImportResult extends ProjectStateResponse {
  imported_count: number;
}

export interface ProjectListItem {
  project_id: string;
  title: string;
  workflow_stage: string;
  updated_at: string;
  project_root: string;
  state_path: string;
  need_reference_recommendation: boolean;
  processed_pdf_count: number;
  recommended_reference_count: number;
}

export interface ProjectListResponse {
  projects: ProjectListItem[];
}

export interface OutlineNode {
  id: string;
  level: number;
  title: string;
  children: OutlineNode[];
}

export interface OutlineTree {
  title: string;
  outline: OutlineNode[];
}

export interface ConfirmedOutlineNode {
  id: string;
  level: number;
  title: string;
  enabled: boolean;
  must_be_separate_block: boolean;
  children: ConfirmedOutlineNode[];
}

export interface ConfirmedOutlineTree {
  title: string;
  outline: ConfirmedOutlineNode[];
}

export interface OutlineImportResult extends ProjectStateResponse {
  parse_result: {
    warnings: string[];
    raw_snapshot_path?: string | null;
    normalized_snapshot_path?: string | null;
  };
}

export interface ChunkPlanBlock {
  block_index: number;
  title: string;
  outline_node_ids: string[];
  goal: string;
  minimum_words: number;
  citation_focus: string[];
}

export interface ChunkPlan {
  total_blocks: number;
  blocks: ChunkPlanBlock[];
}

export interface ChunkPlanImportResult extends ProjectStateResponse {
  parse_result: {
    warnings: string[];
    raw_snapshot_path?: string | null;
    normalized_snapshot_path?: string | null;
  };
}

export interface PromptPreviewResponse {
  project_id: string;
  prompt_name: string;
  prompt_text: string;
  prompt_snapshot_path: string;
  workflow_stage: string;
  model_hint?: string;
  instructions?: string[];
}

export interface CompressedContextPayload {
  covered_blocks: number[];
  compressed_context: {
    narrative_summary: string;
    key_claims: string[];
    used_citations: string[];
    pending_topics: string[];
    style_constraints: string[];
  };
}

export interface GeneratedBlockState {
  block_index: number;
  block_title: string;
  raw_ai_text: string;
  normalized_json?: Record<string, unknown> | null;
  compressed_context_raw_ai_text: string;
  compressed_context_json?: CompressedContextPayload | null;
  status: string;
}

export interface BlockImportResult extends ProjectStateResponse {
  block_index: number;
  parse_result: {
    warnings: string[];
    raw_snapshot_path?: string | null;
    normalized_snapshot_path?: string | null;
  };
}

export interface ExportHistoryItem {
  output_path: string;
  exported_at: string;
  reference_count: number;
  log_path: string;
}

export interface ExportProjectResult extends ProjectStateResponse {
  output_path: string;
  log_path: string;
  reference_count: number;
  message: string;
  export_history?: ExportHistoryItem[];
}

// API Configuration types
export interface LLMProviderConfig {
  provider_id: string;
  name: string;
  api_type: string;
  base_url: string | null;
  model: string;
  enabled: boolean;
  api_key?: string;
}

export interface NotebookLMConfig {
  api_key: string;
  enabled: boolean;
  model: string;
}

export interface APIConfig {
  providers: LLMProviderConfig[];
  notebooklm: NotebookLMConfig;
  default_provider: string;
  schema_version: string;
}

export interface ProviderStatus {
  provider_id: string;
  name: string;
  configured: boolean;
  has_api_key: boolean;
  status: string;
}

export interface UpdateProviderRequest {
  api_key?: string;
  model?: string;
  base_url?: string;
  enabled?: boolean;
}

export interface UpdateNotebookLMRequest {
  api_key?: string;
  enabled?: boolean;
}

export interface SetDefaultProviderRequest {
  provider_id: string;
}

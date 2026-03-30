import type { ProjectListItem } from "../types";

interface ProjectListPanelProps {
  projects: ProjectListItem[];
  currentProjectId?: string | null;
  onLoadProject: (projectId: string) => void;
  onRefresh: () => void;
  onChooseWorkspace: () => void;
}

function ProjectListPanel({
  projects,
  currentProjectId,
  onLoadProject,
  onRefresh,
  onChooseWorkspace,
}: ProjectListPanelProps) {
  return (
    <section className="card">
      <div className="section-head">
        <div>
          <p className="section-kicker">Workspace</p>
          <h2>已有项目</h2>
        </div>
        <div className="mini-actions">
          <button className="ghost-button" onClick={onRefresh}>
            刷新列表
          </button>
          <button className="secondary-button" onClick={onChooseWorkspace}>
            切换工作空间
          </button>
        </div>
      </div>

      {projects.length ? (
        <div className="project-list">
          {projects.map((project) => (
            <button
              key={project.project_id}
              className={`project-list-item ${
                currentProjectId === project.project_id ? "project-list-item-active" : ""
              }`}
              onClick={() => onLoadProject(project.project_id)}
            >
              <div className="project-list-title-row">
                <strong>{project.title}</strong>
                <span className={`badge badge-${workflowTone(project.workflow_stage)}`}>
                  {project.workflow_stage}
                </span>
              </div>
              <p className="project-list-meta">
                {project.need_reference_recommendation ? "推荐文献路线" : "已有 PDF 路线"} · 已入库
                {" "}
                {project.processed_pdf_count} / 推荐 {project.recommended_reference_count}
              </p>
              <p className="project-list-meta">最近更新：{formatTimestamp(project.updated_at)}</p>
            </button>
          ))}
        </div>
      ) : (
        <p className="empty-state">当前工作空间还没有项目。</p>
      )}
    </section>
  );
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function workflowTone(stage: string) {
  if (
    stage === "outline_editing" ||
    stage === "chunk_planning" ||
    stage === "block_generation" ||
    stage === "done"
  ) {
    return "success";
  }
  if (stage === "pdf_processing") {
    return "warning";
  }
  return "neutral";
}

export default ProjectListPanel;

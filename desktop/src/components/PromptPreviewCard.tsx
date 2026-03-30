import type { PromptPreviewResponse } from "../types";

interface PromptPreviewCardProps {
  preview: PromptPreviewResponse | null;
  onOpenSnapshot?: (path: string) => void;
}

function PromptPreviewCard({ preview, onOpenSnapshot }: PromptPreviewCardProps) {
  if (!preview) {
    return null;
  }

  return (
    <div className="prompt-preview">
      <div className="section-head">
        <div>
          <p className="section-kicker">Prompt Preview</p>
          <h3>{preview.prompt_name}</h3>
        </div>
        <div className="mini-actions">
          <button
            className="ghost-button"
            onClick={() => void navigator.clipboard.writeText(preview.prompt_text)}
          >
            复制 Prompt
          </button>
          {onOpenSnapshot ? (
            <button
              className="ghost-button"
              onClick={() => onOpenSnapshot(preview.prompt_snapshot_path)}
            >
              打开快照
            </button>
          ) : null}
        </div>
      </div>
      
      {/* 模型提示和操作说明 */}
      {preview.model_hint && (
        <div className="model-hint">
          <span className="hint-label">推荐模型：</span>
          <span className="hint-value">{preview.model_hint}</span>
        </div>
      )}
      
      {preview.instructions && preview.instructions.length > 0 && (
        <div className="instructions">
          <span className="hint-label">操作步骤：</span>
          <ul>
            {preview.instructions.map((instruction, index) => (
              <li key={index}>{instruction}</li>
            ))}
          </ul>
        </div>
      )}
      
      <textarea rows={12} value={preview.prompt_text} readOnly />
    </div>
  );
}

export default PromptPreviewCard;

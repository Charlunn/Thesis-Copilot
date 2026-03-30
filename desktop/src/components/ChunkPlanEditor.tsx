import type { ChunkPlan, PromptPreviewResponse } from "../types";
import PromptPreviewCard from "./PromptPreviewCard";

interface ChunkPlanEditorProps {
  plan: ChunkPlan | null;
  promptPreview: PromptPreviewResponse | null;
  rawText: string;
  importDisabled: boolean;
  saveDisabled: boolean;
  onRawTextChange: (value: string) => void;
  onPlanChange: (plan: ChunkPlan) => void;
  onGeneratePrompt: () => void;
  onImport: () => void;
  onSave: () => void;
  onOpenSnapshot?: (path: string) => void;
}

function ChunkPlanEditor({
  plan,
  promptPreview,
  rawText,
  importDisabled,
  saveDisabled,
  onRawTextChange,
  onPlanChange,
  onGeneratePrompt,
  onImport,
  onSave,
  onOpenSnapshot,
}: ChunkPlanEditorProps) {
  return (
    <section className="card wide-card">
      <div className="section-head">
        <div>
          <p className="section-kicker">Step 7</p>
          <h2>切块规划</h2>
        </div>
        <div className="mini-actions">
          <button className="ghost-button" disabled={importDisabled} onClick={onGeneratePrompt}>
            生成切块 Prompt
          </button>
          <button className="primary-button" disabled={importDisabled} onClick={onImport}>
            导入切块 JSON
          </button>
          <button className="secondary-button" disabled={saveDisabled} onClick={onSave}>
            保存确认版切块
          </button>
        </div>
      </div>

      <p className="note">
        这一步建议使用通用 LLM。先生成 Prompt，复制给外部模型拿回严格 JSON，
        再在下方微调和确认。
      </p>

      <PromptPreviewCard preview={promptPreview} onOpenSnapshot={onOpenSnapshot} />

      <textarea
        rows={10}
        value={rawText}
        onChange={(event) => onRawTextChange(event.target.value)}
        placeholder="在这里粘贴切块规划 JSON..."
      />

      {plan ? (
        <div className="chunk-plan-editor">
          <label>
            总块数
            <input
              type="number"
              min={1}
              value={plan.total_blocks}
              onChange={(event) =>
                onPlanChange({
                  ...plan,
                  total_blocks: Math.max(1, Number(event.target.value || 1)),
                })
              }
            />
          </label>

          <div className="chunk-plan-list">
            {plan.blocks.map((block, index) => (
              <div key={block.block_index} className="chunk-block-card">
                <div className="chunk-block-head">
                  <strong>块 {block.block_index}</strong>
                  <span>{block.outline_node_ids.join(", ")}</span>
                </div>

                <label>
                  块标题
                  <input
                    value={block.title}
                    onChange={(event) =>
                      onPlanChange(updateBlock(plan, index, { title: event.target.value }))
                    }
                  />
                </label>

                <label>
                  写作目标
                  <textarea
                    rows={3}
                    value={block.goal}
                    onChange={(event) =>
                      onPlanChange(updateBlock(plan, index, { goal: event.target.value }))
                    }
                  />
                </label>

                <div className="grid-two">
                  <label>
                    最低字数
                    <input
                      type="number"
                      min={1}
                      value={block.minimum_words}
                      onChange={(event) =>
                        onPlanChange(
                          updateBlock(plan, index, {
                            minimum_words: Math.max(1, Number(event.target.value || 1)),
                          }),
                        )
                      }
                    />
                  </label>

                  <label>
                    覆盖节点
                    <input
                      value={block.outline_node_ids.join(", ")}
                      onChange={(event) =>
                        onPlanChange(
                          updateBlock(plan, index, {
                            outline_node_ids: splitCsv(event.target.value),
                          }),
                        )
                      }
                    />
                  </label>
                </div>

                <label>
                  重点引用主题
                  <input
                    value={block.citation_focus.join(", ")}
                    onChange={(event) =>
                      onPlanChange(
                        updateBlock(plan, index, {
                          citation_focus: splitCsv(event.target.value),
                        }),
                      )
                    }
                  />
                </label>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="empty-state">确认版大纲保存后，这里就可以推进切块规划。</p>
      )}
    </section>
  );
}

function splitCsv(value: string) {
  return value
    .split(/[，,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function updateBlock(plan: ChunkPlan, index: number, patch: Partial<ChunkPlan["blocks"][number]>) {
  const nextBlocks = [...plan.blocks];
  nextBlocks[index] = { ...nextBlocks[index], ...patch };
  return { ...plan, blocks: nextBlocks };
}

export default ChunkPlanEditor;

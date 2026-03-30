import type { GeneratedBlockState, PromptPreviewResponse } from "../types";
import PromptPreviewCard from "./PromptPreviewCard";

interface GenerationWorkbenchProps {
  blocks: GeneratedBlockState[];
  currentBlockIndex: number;
  totalBlocks: number;
  generationPrompt: PromptPreviewResponse | null;
  compressPrompt: PromptPreviewResponse | null;
  blockRawText: string;
  compressRawText: string;
  generateBlockDisabled?: boolean;
  importBlockDisabled?: boolean;
  generateCompressDisabled?: boolean;
  importCompressDisabled?: boolean;
  blockInputDisabled?: boolean;
  compressInputDisabled?: boolean;
  onBlockRawTextChange: (value: string) => void;
  onCompressRawTextChange: (value: string) => void;
  onGenerateBlockPrompt: () => void;
  onImportBlock: () => void;
  onGenerateCompressPrompt: () => void;
  onImportCompress: () => void;
  onOpenSnapshot?: (path: string) => void;
}

function GenerationWorkbench({
  blocks,
  currentBlockIndex,
  totalBlocks,
  generationPrompt,
  compressPrompt,
  blockRawText,
  compressRawText,
  generateBlockDisabled = false,
  importBlockDisabled = false,
  generateCompressDisabled = false,
  importCompressDisabled = false,
  blockInputDisabled = false,
  compressInputDisabled = false,
  onBlockRawTextChange,
  onCompressRawTextChange,
  onGenerateBlockPrompt,
  onImportBlock,
  onGenerateCompressPrompt,
  onImportCompress,
  onOpenSnapshot,
}: GenerationWorkbenchProps) {
  const activeBlock = blocks.find((block) => block.block_index === currentBlockIndex) ?? null;

  return (
    <section className="card wide-card">
      <div className="section-head">
        <div>
          <p className="section-kicker">Step 8</p>
          <h2>正文块工作台</h2>
        </div>
        <div className="summary-inline">
          <strong>
            当前块：{currentBlockIndex || "-"} / {totalBlocks || "-"}
          </strong>
          {activeBlock ? <span>{activeBlock.block_title}</span> : null}
        </div>
      </div>

      {blocks.length ? (
        <>
          <p className="note">
            先用 NotebookLM 生成当前块正文，再用通用 LLM 压缩上下文，之后系统会推进到下一块。
          </p>

          <div className="generation-grid">
            <div className="generation-panel">
              <div className="section-head">
                <div>
                  <p className="section-kicker">NotebookLM</p>
                  <h3>当前块生成 Prompt</h3>
                </div>
                <div className="mini-actions">
                  <button
                    className="ghost-button"
                    disabled={generateBlockDisabled}
                    onClick={onGenerateBlockPrompt}
                  >
                    生成 Prompt
                  </button>
                  <button
                    className="primary-button"
                    disabled={importBlockDisabled}
                    onClick={onImportBlock}
                  >
                    导入块 JSON
                  </button>
                </div>
              </div>

              <PromptPreviewCard preview={generationPrompt} onOpenSnapshot={onOpenSnapshot} />

              <textarea
                rows={9}
                value={blockRawText}
                onChange={(event) => onBlockRawTextChange(event.target.value)}
                placeholder="把 NotebookLM 返回的块 JSON 粘贴到这里..."
                disabled={blockInputDisabled}
              />
            </div>

            <div className="generation-panel">
              <div className="section-head">
                <div>
                  <p className="section-kicker">通用 LLM</p>
                  <h3>上下文压缩 Prompt</h3>
                </div>
                <div className="mini-actions">
                  <button
                    className="ghost-button"
                    disabled={generateCompressDisabled}
                    onClick={onGenerateCompressPrompt}
                  >
                    生成压缩 Prompt
                  </button>
                  <button
                    className="secondary-button"
                    disabled={importCompressDisabled}
                    onClick={onImportCompress}
                  >
                    导入压缩 JSON
                  </button>
                </div>
              </div>

              <PromptPreviewCard preview={compressPrompt} onOpenSnapshot={onOpenSnapshot} />

              <textarea
                rows={9}
                value={compressRawText}
                onChange={(event) => onCompressRawTextChange(event.target.value)}
                placeholder="把通用 LLM 返回的 compressed_context JSON 粘贴到这里..."
                disabled={compressInputDisabled}
              />
            </div>
          </div>

          <div className="generation-status-list">
            {blocks.map((block) => (
              <div key={block.block_index} className="generation-status-card">
                <div className="generation-status-head">
                  <strong>
                    {block.block_index}. {block.block_title}
                  </strong>
                  <span className={`badge badge-${blockStatusTone(block, totalBlocks)}`}>
                    {blockStatusLabel(block, totalBlocks)}
                  </span>
                </div>
                <p className="note">{blockStatusDescription(block, totalBlocks)}</p>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="empty-state">确认版切块方案保存后，这里会启用块生成工作台。</p>
      )}
    </section>
  );
}

function blockStatusTone(block: GeneratedBlockState, totalBlocks: number) {
  if (block.normalized_json && (block.compressed_context_json || block.block_index === totalBlocks)) {
    return "success";
  }
  if (block.normalized_json) {
    return "warning";
  }
  return "neutral";
}

function blockStatusLabel(block: GeneratedBlockState, totalBlocks: number) {
  if (block.normalized_json && (block.compressed_context_json || block.block_index === totalBlocks)) {
    return "完成";
  }
  if (block.normalized_json) {
    return "待压缩";
  }
  return "待生成";
}

function blockStatusDescription(block: GeneratedBlockState, totalBlocks: number) {
  const contentStatus = block.normalized_json ? "正文：已导入" : "正文：待导入";
  if (block.block_index === totalBlocks) {
    return `${contentStatus} · 压缩：最后一块无需压缩`;
  }
  return `${contentStatus} · 压缩：${block.compressed_context_json ? "已导入" : "待导入"}`;
}

export default GenerationWorkbench;

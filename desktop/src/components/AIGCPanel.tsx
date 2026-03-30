import { useState } from "react";

interface AIGCPanelProps {
  blocks: Array<{block_index: number; block_title: string; normalized_json?: any}>;
  onReduce?: (content: string) => void;
}

interface AIGCResult {
  score: number;
  level: string;
  suggestion: string;
  needs_reduction: boolean;
  reduction_count: number;
  reduction_prompt: string;
  model_hint: string;
  instructions: string[];
}

export default function AIGCPanel({ blocks, onReduce }: AIGCPanelProps) {
  const [aigcScore, setAigcScore] = useState<number | null>(null);
  const [manualScore, setManualScore] = useState("");
  const [result, setResult] = useState<AIGCResult | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);

  function extractContent() {
    const parts: string[] = [];
    for (const block of blocks) {
      parts.push(`【${block.block_title}】`);
      const content = block.normalized_json?.content || [];
      for (const el of content) {
        if (el.type === "p" && el.text) parts.push(el.text);
      }
    }
    return parts.join("\n\n");
  }

  function getScoreColor(score: number) {
    if (score < 30) return "success";
    if (score < 50) return "warning";
    return "error";
  }

  function handleAnalyze() {
    const score = parseInt(manualScore);
    if (isNaN(score) || score < 0 || score > 100) {
      alert("请输入 0-100 之间的数字");
      return;
    }
    setAigcScore(score);
    
    const levels: Record<string, {level: string; suggestion: string; needs_reduction: boolean; reduction_count: number}> = {
      low: { level: "low", suggestion: "AIGC 率较低，可以正常导出", needs_reduction: false, reduction_count: 0 },
      medium: { level: "medium", suggestion: "AIGC 率中等，建议进行一次降低处理后再导出", needs_reduction: true, reduction_count: 1 },
      high: { level: "high", suggestion: "AIGC 率较高，必须进行降低处理后再导出", needs_reduction: true, reduction_count: 1 },
      very_high: { level: "very_high", suggestion: "AIGC 率很高，必须多次降低处理", needs_reduction: true, reduction_count: 2 },
    };

    let levelData;
    if (score < 30) levelData = levels.low;
    else if (score < 50) levelData = levels.medium;
    else if (score < 70) levelData = levels.high;
    else levelData = levels.very_high;

    const content = extractContent();
    setResult({
      score,
      level: levelData.level,
      suggestion: levelData.suggestion,
      needs_reduction: levelData.needs_reduction,
      reduction_count: levelData.reduction_count,
      reduction_prompt: `你是学术论文润色专家。请对以下论文内容进行深度改写，使其更加自然、真实，降低被 AI 检测工具识别的可能性。

【改写原则】
1. 打破完美句式：主动句、被动句、长句、短句交替使用
2. 增加个人视角：适当加入"笔者认为"、"从实践角度看"等表达
3. 使用口语化连接词："所以"、"不过"、"其实"代替"因此"、"然而"
4. 调整段落结构：段落长度要有自然变化
5. 保留专业性：保持学术论文的专业水准

【待处理内容】
${content}`,
      model_hint: "通用大模型（如 DeepSeek、GLM 等）",
      instructions: [
        "1. 点击「生成降低 Prompt」按钮",
        "2. 将 Prompt 粘贴给大模型处理",
        "3. 将处理后的内容替换到软件中",
      ],
    });
  }

  return (
    <div className="aigc-panel">
      <h3>📊 AIGC 检测与降低</h3>
      
      <div className="aigc-input">
        <label>
          请使用第三方 AIGC 检测工具检测论文后，输入检测到的 AIGC 率（0-100）：
          <input
            type="number"
            min="0"
            max="100"
            value={manualScore}
            onChange={(e) => setManualScore(e.target.value)}
            placeholder="输入检测到的百分比"
          />
        </label>
        <button className="primary-button" onClick={handleAnalyze}>
          分析 AIGC 率
        </button>
      </div>

      {result && (
        <div className={`aigc-result ${result.level}`}>
          <div className="score-display">
            <span className="score-label">AIGC 率：</span>
            <span className={`score-value badge-${getScoreColor(result.score)}`}>
              {result.score}%
            </span>
          </div>
          
          <p className="suggestion">{result.suggestion}</p>
          
          {result.needs_reduction && (
            <div className="reduction-section">
              <button 
                className="secondary-button"
                onClick={() => setShowPrompt(!showPrompt)}
              >
                {showPrompt ? "隐藏降低 Prompt" : "生成降低 Prompt"}
              </button>
              
              {showPrompt && (
                <div className="reduction-prompt">
                  <p className="model-hint">推荐模型：{result.model_hint}</p>
                  <ul className="instructions">
                    {result.instructions.map((inst, i) => <li key={i}>{inst}</li>)}
                  </ul>
                  <textarea
                    rows={15}
                    value={result.reduction_prompt}
                    readOnly
                  />
                  <button 
                    className="ghost-button"
                    onClick={() => navigator.clipboard.writeText(result.reduction_prompt)}
                  >
                    复制 Prompt
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

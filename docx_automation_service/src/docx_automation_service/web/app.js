const form = document.getElementById("run-form");
const fileInput = document.getElementById("file");
const rawTextInput = document.getElementById("raw_text");
const modeInput = document.getElementById("mode");
const topicInput = document.getElementById("topic_hint");
const termsInput = document.getElementById("preserve_terms");
const modelInput = document.getElementById("model_name");
const reasoningInput = document.getElementById("enable_reasoning");
const aigcStrategyInput = document.getElementById("aigc_reduction_strategy");
const enableLayer2Input = document.getElementById("enable_structural_rebuild");
const layer2ToggleWrap = document.getElementById("layer2-toggle-wrap");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const outputEl = document.getElementById("output");
const reportBtn = document.getElementById("report-btn");
const downloadBtn = document.getElementById("download-btn");
const cancelBtn = document.getElementById("cancel-btn");
const stageEl = document.getElementById("stage");
const progressTextEl = document.getElementById("progress-text");
const progressBarEl = document.getElementById("progress-bar");
const progressDetailEl = document.getElementById("progress-detail");

let runInfo = null;
let pollingTimer = null;
const LAST_RUN_KEY = "docx_automation_last_run";

function setStatus(msg) {
  statusEl.textContent = msg;
}

function setOutput(obj) {
  outputEl.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
}

function setReportOutput(report) {
  const chunkTotal = report.chunk_total ?? 0;
  const flaggedTotal = report.flagged_total ?? 0;
  const failedTotal = report.rewrite_failed_total ?? 0;
  const ratio = chunkTotal > 0 ? ((flaggedTotal / chunkTotal) * 100).toFixed(1) : "0.0";

  const chunks = Array.isArray(report.chunks) ? report.chunks : [];
  const topFlagged = chunks
    .filter((x) => x.flagged)
    .sort((a, b) => (b.aigc_score || 0) - (a.aigc_score || 0))
    .slice(0, 8);

  const lines = [
    "任务报告",
    "-------------------------",
    `任务ID：${report.run_id || "-"}`,
    `模式：${report.mode || "-"}`,
    `段落总数：${chunkTotal}`,
    `命中风险段落：${flaggedTotal}（${ratio}%）`,
    `改写失败段落：${failedTotal}`,
    "",
    "高风险段落（最多展示 8 条）：",
  ];

  if (!topFlagged.length) {
    lines.push("- 无");
  } else {
    topFlagged.forEach((item) => {
      lines.push(
        `- ${item.chunk_id} | similarity=${Number(item.similarity_score || 0).toFixed(3)} | aigc=${Number(item.aigc_score || 0).toFixed(3)}`
      );
    });
  }

  if (Array.isArray(report.rewrite_failures) && report.rewrite_failures.length) {
    lines.push("", "失败详情：");
    report.rewrite_failures.slice(0, 10).forEach((f) => {
      lines.push(`- ${f.chunk_id}: ${f.error}`);
    });
  }

  outputEl.textContent = lines.join("\n");
}

function setProgress(status) {
  const percent = Math.max(0, Math.min(100, Number(status.progress_percent || 0)));
  const stage = status.current_stage || "等待中";
  const current = status.current_chunk || 0;
  const total = status.total_chunks || 0;
  const eta = status.eta_seconds == null ? "--" : `${status.eta_seconds}s`;

  progressBarEl.style.width = `${percent}%`;
  progressTextEl.textContent = `${percent.toFixed(1)}%`;
  stageEl.textContent = `阶段：${stage}`;
  progressDetailEl.textContent = `段落：${current} / ${total}，预计剩余：${eta}`;
}

function stopPolling() {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
}

function enableActionsFromStatus(status) {
  reportBtn.disabled = status.status !== "done" && status.status !== "failed";
  const hasResult = status.mode === "rewrite" || status.mode === "deep_rewrite";
  downloadBtn.disabled = !(status.status === "done" && hasResult);
  cancelBtn.disabled = !(status.status === "running" || status.status === "queued");
}

async function refreshStatus() {
  if (!runInfo || !runInfo.run_id) return;
  try {
    const status = await fetchJson(`/v1/runs/${runInfo.run_id}/status`);
    runInfo = { ...runInfo, ...status };
    localStorage.setItem(LAST_RUN_KEY, JSON.stringify(runInfo));

    setProgress(status);
    enableActionsFromStatus(status);

    if (status.status === "running" || status.status === "queued") {
      setStatus(status.message || "任务处理中...");
      return;
    }

    stopPolling();
    if (status.status === "done") {
      setStatus("任务已完成，可查看报告");
      setOutput(status);
    } else if (status.status === "canceled") {
      setStatus("任务已中断");
      setOutput(status.message || "任务已中断");
    } else if (status.status === "failed") {
      setStatus("任务失败");
      setOutput(status.error || "任务失败");
    }
  } catch (err) {
    setStatus("状态查询失败，稍后重试");
    setOutput(err.message || String(err));
  }
}

function startPolling() {
  stopPolling();
  pollingTimer = setInterval(refreshStatus, 1500);
  refreshStatus();
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const hasFile = !!(fileInput.files && fileInput.files[0]);
  const rawText = (rawTextInput.value || "").trim();

  if (!hasFile && !rawText) {
    setStatus("请上传 DOCX 或粘贴文本");
    return;
  }

  submitBtn.disabled = true;
  reportBtn.disabled = true;
  downloadBtn.disabled = true;
  cancelBtn.disabled = true;
  runInfo = null;

  try {
    setStatus("正在提交任务...");
    const fd = new FormData();
    if (hasFile) {
      fd.append("file", fileInput.files[0]);
    }
    if (rawText) {
      fd.append("raw_text", rawText);
    }
    fd.append("mode", modeInput.value);
    if (topicInput.value.trim()) {
      fd.append("topic_hint", topicInput.value.trim());
    }
    if (termsInput.value.trim()) {
      fd.append("preserve_terms", termsInput.value.trim());
    }
    if (modelInput.value.trim()) {
      fd.append("model_name", modelInput.value.trim());
    }
    fd.append("enable_reasoning", reasoningInput.checked ? "true" : "false");
    const strategy = aigcStrategyInput ? aigcStrategyInput.value : "";
    if (strategy) {
      fd.append("aigc_reduction_strategy", strategy);
    }
    fd.append("enable_structural_rebuild", (enableLayer2Input && enableLayer2Input.checked) ? "true" : "false");

    const created = await fetchJson("/v1/runs", { method: "POST", body: fd });
    runInfo = created;
    localStorage.setItem(LAST_RUN_KEY, JSON.stringify(runInfo));

    setStatus("任务已提交，正在后台处理中...");
    setProgress(created);
    setOutput(created);
    startPolling();
  } catch (err) {
    setStatus("提交失败");
    setOutput(err.message || String(err));
  } finally {
    submitBtn.disabled = false;
  }
});

reportBtn.addEventListener("click", async () => {
  if (!runInfo || !runInfo.run_id) return;
  try {
    setStatus("正在获取报告...");
    const report = await fetchJson(`/v1/runs/${runInfo.run_id}/report`);
    setStatus("报告已获取");
    setReportOutput(report);
  } catch (err) {
    setStatus("报告获取失败");
    setOutput(err.message || String(err));
  }
});

downloadBtn.addEventListener("click", () => {
  if (!runInfo || !runInfo.run_id) return;
  window.open(`/v1/runs/${runInfo.run_id}/result`, "_blank");
});

cancelBtn.addEventListener("click", async () => {
  if (!runInfo || !runInfo.run_id) return;
  try {
    const result = await fetchJson(`/v1/runs/${runInfo.run_id}`, { method: "DELETE" });
    setStatus(result.message || "任务已中断");
    stopPolling();
    enableActionsFromStatus({ ...runInfo, status: "canceled" });
    setOutput(result);
  } catch (err) {
    setStatus("中断任务失败");
    setOutput(err.message || String(err));
  }
});

async function restoreLastRun() {
  const raw = localStorage.getItem(LAST_RUN_KEY);
  if (!raw) return;

  try {
    runInfo = JSON.parse(raw);
  } catch {
    localStorage.removeItem(LAST_RUN_KEY);
    return;
  }

  if (!runInfo || !runInfo.run_id) return;

  setStatus("已恢复上次任务，正在同步状态...");
  startPolling();
}

restoreLastRun();

// Show/hide the layer2 toggle based on strategy selection
if (aigcStrategyInput && layer2ToggleWrap) {
  function updateLayer2Visibility() {
    const show = aigcStrategyInput.value === "strategy_2";
    layer2ToggleWrap.style.display = show ? "" : "none";
  }
  aigcStrategyInput.addEventListener("change", updateLayer2Visibility);
  updateLayer2Visibility();
}

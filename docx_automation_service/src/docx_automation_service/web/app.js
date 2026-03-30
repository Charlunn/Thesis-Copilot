const form = document.getElementById("run-form");
const fileInput = document.getElementById("file");
const modeInput = document.getElementById("mode");
const topicInput = document.getElementById("topic_hint");
const termsInput = document.getElementById("preserve_terms");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const outputEl = document.getElementById("output");
const reportBtn = document.getElementById("report-btn");
const downloadBtn = document.getElementById("download-btn");

let runInfo = null;

function setStatus(msg) {
  statusEl.textContent = msg;
}

function setOutput(obj) {
  outputEl.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
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
  if (!fileInput.files || !fileInput.files[0]) {
    setStatus("请先选择 DOCX 文件");
    return;
  }

  submitBtn.disabled = true;
  reportBtn.disabled = true;
  downloadBtn.disabled = true;
  runInfo = null;

  try {
    setStatus("正在提交任务...");
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    fd.append("mode", modeInput.value);
    if (topicInput.value.trim()) {
      fd.append("topic_hint", topicInput.value.trim());
    }
    if (termsInput.value.trim()) {
      fd.append("preserve_terms", termsInput.value.trim());
    }

    const created = await fetchJson("/v1/runs", { method: "POST", body: fd });
    runInfo = created;

    setStatus("任务已完成，可查看报告");
    setOutput(created);
    reportBtn.disabled = false;
    downloadBtn.disabled = modeInput.value !== "rewrite";
  } catch (err) {
    setStatus("提交失败");
    setOutput(err.message || String(err));
  } finally {
    submitBtn.disabled = false;
  }
});

reportBtn.addEventListener("click", async () => {
  if (!runInfo || !runInfo.report_url) return;
  try {
    setStatus("正在获取报告...");
    const report = await fetchJson(runInfo.report_url);
    setStatus("报告已获取");
    setOutput(report);
  } catch (err) {
    setStatus("报告获取失败");
    setOutput(err.message || String(err));
  }
});

downloadBtn.addEventListener("click", () => {
  if (!runInfo || !runInfo.result_url) return;
  window.open(runInfo.result_url, "_blank");
});

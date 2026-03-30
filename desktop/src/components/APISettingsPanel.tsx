import { useEffect, useState } from "react";

import type { APIConfig, LLMProviderConfig } from "../types";

interface APISettingsPanelProps {
  onClose?: () => void;
}

export default function APISettingsPanel({ onClose }: APISettingsPanelProps) {
  const [config, setConfig] = useState<APIConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<"providers" | "notebooklm">("providers");
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [tempApiKey, setTempApiKey] = useState("");
  const [tempModel, setTempModel] = useState("");
  const [tempBaseUrl, setTempBaseUrl] = useState("");
  const [notebooklmApiKey, setNotebooklmApiKey] = useState("");

  const quickPresets: Record<string, { model: string; baseUrl: string }> = {
    openai: { model: "gpt-4.1-mini", baseUrl: "https://api.openai.com/v1" },
    deepseek: { model: "deepseek-chat", baseUrl: "https://api.deepseek.com/v1" },
    anthropic: { model: "claude-sonnet-4-20250514", baseUrl: "https://api.anthropic.com/v1" },
    zhipu: { model: "glm-4-flash", baseUrl: "https://open.bigmodel.cn/api/paas/v4" },
    qwen: { model: "qwen-plus", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  };

  useEffect(() => {
    void loadConfig();
  }, []);

  async function loadConfig() {
    setLoading(true);
    try {
      const data = await window.qnuCopilot.getConfig();
      setConfig(data);
    } catch (error) {
      console.error("Failed to load config:", error);
    } finally {
      setLoading(false);
    }
  }

  async function updateProvider(providerId: string) {
    setSaving(true);
    try {
      const update: Record<string, string | boolean> = {};
      if (tempApiKey) update.api_key = tempApiKey;
      if (tempModel) update.model = tempModel;
      if (tempBaseUrl) update.base_url = tempBaseUrl;

      const data = await window.qnuCopilot.updateProvider(providerId, update);
      setConfig(data);
      setEditingProvider(null);
      setTempApiKey("");
      setTempModel("");
      setTempBaseUrl("");
    } catch (error) {
      console.error("Failed to update provider:", error);
    } finally {
      setSaving(false);
    }
  }

  async function updateNotebookLM() {
    setSaving(true);
    try {
      const data = await window.qnuCopilot.updateNotebookLM({
        api_key: notebooklmApiKey,
        enabled: true,
      });
      setConfig(data);
      setNotebooklmApiKey("");
    } catch (error) {
      console.error("Failed to update NotebookLM:", error);
    } finally {
      setSaving(false);
    }
  }

  async function setDefaultProvider(providerId: string) {
    try {
      const data = await window.qnuCopilot.setDefaultProvider({ provider_id: providerId });
      setConfig(data);
    } catch (error) {
      console.error("Failed to set default provider:", error);
    }
  }

  function startEditProvider(provider: LLMProviderConfig) {
    setEditingProvider(provider.provider_id);
    setTempModel(provider.model);
    setTempBaseUrl(provider.base_url || "");
  }

  function applyQuickPreset(provider: LLMProviderConfig) {
    const preset = quickPresets[provider.provider_id];
    if (!preset) {
      return;
    }
    setTempModel(preset.model);
    setTempBaseUrl(preset.baseUrl);
    if (editingProvider !== provider.provider_id) {
      setEditingProvider(provider.provider_id);
    }
  }

  if (loading) {
    return (
      <div className="api-settings-panel">
        <div className="panel-header">
          <h2>API 配置</h2>
          {onClose && <button className="ghost-button" onClick={onClose}>关闭</button>}
        </div>
        <p className="loading-text">加载中...</p>
      </div>
    );
  }

  return (
    <div className="api-settings-panel">
      <div className="panel-header">
        <h2>API 配置</h2>
        {onClose && <button className="ghost-button" onClick={onClose}>关闭</button>}
      </div>

      <div className="settings-tabs">
        <button
          className={`tab-button ${activeTab === "providers" ? "active" : ""}`}
          onClick={() => setActiveTab("providers")}
        >
          大模型服务商
        </button>
        <button
          className={`tab-button ${activeTab === "notebooklm" ? "active" : ""}`}
          onClick={() => setActiveTab("notebooklm")}
        >
          NotebookLM 专用
        </button>
      </div>

      {activeTab === "providers" && config && (
        <div className="providers-list">
          <p className="settings-note">
            选择您要使用的大模型服务商。配置完成后，该模型将用于生成推荐文献、大纲和切块等 Prompt。
            点击“快速填充”可自动带入主流服务商常用地址与模型，再补充 API Key 即可。
          </p>

          {config.providers.map((provider) => (
            <div key={provider.provider_id} className="provider-card">
              <div className="provider-header">
                <div className="provider-info">
                  <h3>{provider.name}</h3>
                  <span className="provider-type">{provider.api_type}</span>
                </div>
                <div className="provider-actions">
                  {config.default_provider === provider.provider_id ? (
                    <span className="badge badge-success">默认</span>
                  ) : (
                    <button
                      className="ghost-button small"
                      onClick={() => setDefaultProvider(provider.provider_id)}
                    >
                      设为默认
                    </button>
                  )}
                  {quickPresets[provider.provider_id] ? (
                    <button
                      className="ghost-button small"
                      onClick={() => applyQuickPreset(provider)}
                    >
                      快速填充
                    </button>
                  ) : null}
                </div>
              </div>

              <div className="provider-config">
                <div className="config-row">
                  <span className="config-label">API Key</span>
                  {editingProvider === provider.provider_id ? (
                    <input
                      type="password"
                      value={tempApiKey}
                      onChange={(e) => setTempApiKey(e.target.value)}
                      placeholder="输入新的 API Key"
                    />
                  ) : (
                    <span className="config-value">
                      已保存后端（安全起见不回显）
                    </span>
                  )}
                </div>

                <div className="config-row">
                  <span className="config-label">模型</span>
                  {editingProvider === provider.provider_id ? (
                    <input
                      type="text"
                      value={tempModel}
                      onChange={(e) => setTempModel(e.target.value)}
                      placeholder={provider.model || "例如: gpt-4o"}
                    />
                  ) : (
                    <span className="config-value">{provider.model || "未设置"}</span>
                  )}
                </div>

                <div className="config-row">
                  <span className="config-label">接口地址</span>
                  {editingProvider === provider.provider_id ? (
                    <input
                      type="text"
                      value={tempBaseUrl}
                      onChange={(e) => setTempBaseUrl(e.target.value)}
                      placeholder={provider.base_url || "https://api.example.com/v1"}
                    />
                  ) : (
                    <span className="config-value small">{provider.base_url || "未设置"}</span>
                  )}
                </div>
              </div>

              <div className="provider-footer">
                {editingProvider === provider.provider_id ? (
                  <>
                    <button
                      className="secondary-button"
                      onClick={() => setEditingProvider(null)}
                      disabled={saving}
                    >
                      取消
                    </button>
                    <button
                      className="primary-button"
                      onClick={() => updateProvider(provider.provider_id)}
                      disabled={saving}
                    >
                      {saving ? "保存中..." : "保存"}
                    </button>
                  </>
                ) : (
                  <button
                    className="ghost-button"
                    onClick={() => startEditProvider(provider)}
                  >
                    编辑配置
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === "notebooklm" && config && (
        <div className="notebooklm-section">
          <p className="settings-note">
            NotebookLM 专门用于处理 PDF 文献事实锚定步骤，请填写 API Key 并保存。
          </p>

          <div className="notebooklm-config">
            <div className="config-row">
              <span className="config-label">API Key</span>
              <input
                type="password"
                value={notebooklmApiKey}
                onChange={(e) => setNotebooklmApiKey(e.target.value)}
                placeholder="输入 NotebookLM API Key"
              />
            </div>

            <div className="config-info">
              <p>
                <strong>如何获取 NotebookLM API Key？</strong>
              </p>
              <ol>
                <li>访问 Google AI Studio</li>
                <li>登录您的 Google 账号</li>
                <li>在"API Keys"页面创建新密钥</li>
                <li>复制密钥并粘贴到此处</li>
              </ol>
            </div>
          </div>

          <div className="config-actions">
            <button
              className="primary-button"
              onClick={() => updateNotebookLM()}
              disabled={saving || !notebooklmApiKey}
            >
              {saving ? "保存中..." : "保存 NotebookLM 配置"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

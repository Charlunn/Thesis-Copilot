from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""
    provider_id: str
    name: str
    api_type: str = "openai"  # openai, anthropic, gemini, notebooklm
    base_url: str | None = None
    api_key: str = ""
    model: str = ""
    enabled: bool = True


class NotebookLMConfig(BaseModel):
    """Configuration for NotebookLM API."""
    api_key: str = ""
    enabled: bool = False
    model: str = "notebooklm"


class APIConfig(BaseModel):
    """Global API configuration."""
    providers: list[LLMProviderConfig] = Field(default_factory=list)
    notebooklm: NotebookLMConfig = Field(default_factory=NotebookLMConfig)
    default_provider: str = ""
    schema_version: str = "1.0"

    @classmethod
    def get_default_config(cls) -> APIConfig:
        """Get default configuration with common providers."""
        return cls(
            providers=[
                LLMProviderConfig(
                    provider_id="openai",
                    name="OpenAI",
                    api_type="openai",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o",
                    enabled=True,
                ),
                LLMProviderConfig(
                    provider_id="deepseek",
                    name="DeepSeek",
                    api_type="openai",
                    base_url="https://api.deepseek.com/v1",
                    model="deepseek-chat",
                    enabled=False,
                ),
                LLMProviderConfig(
                    provider_id="anthropic",
                    name="Anthropic (Claude)",
                    api_type="anthropic",
                    base_url="https://api.anthropic.com/v1",
                    model="claude-sonnet-4-20250514",
                    enabled=False,
                ),
                LLMProviderConfig(
                    provider_id="zhipu",
                    name="智谱 GLM",
                    api_type="openai",
                    base_url="https://open.bigmodel.cn/api/paas/v4",
                    model="glm-4-flash",
                    enabled=False,
                ),
                LLMProviderConfig(
                    provider_id="qwen",
                    name="阿里通义千问",
                    api_type="openai",
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    model="qwen-plus",
                    enabled=False,
                ),
                LLMProviderConfig(
                    provider_id="minimax",
                    name="MiniMax",
                    api_type="openai",
                    base_url="https://api.minimax.chat/v1",
                    model="MiniMax-Text-01",
                    enabled=False,
                ),
            ],
            notebooklm=NotebookLMConfig(),
            default_provider="openai",
        )


class APIConfigService:
    """Service for managing API configuration."""

    CONFIG_FILE = "api_config.json"

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.config_path = self.data_root / self.CONFIG_FILE
        self._config: APIConfig | None = None

    def load_config(self) -> APIConfig:
        """Load configuration from file."""
        if self._config is not None:
            return self._config

        if self.config_path.exists():
            try:
                import json
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                self._config = APIConfig.model_validate(data)
            except Exception:
                self._config = APIConfig.get_default_config()
        else:
            self._config = APIConfig.get_default_config()

        return self._config

    def save_config(self, config: APIConfig) -> None:
        """Save configuration to file."""
        import json
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        self._config = config

    def get_config(self) -> APIConfig:
        """Get current configuration."""
        return self.load_config()

    def update_provider(
        self,
        provider_id: str,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        enabled: bool | None = None,
    ) -> APIConfig:
        """Update a specific provider configuration."""
        config = self.load_config()
        
        for provider in config.providers:
            if provider.provider_id == provider_id:
                if api_key is not None:
                    provider.api_key = api_key
                if model is not None:
                    provider.model = model
                if base_url is not None:
                    provider.base_url = base_url
                if enabled is not None:
                    provider.enabled = enabled
                break

        self.save_config(config)
        return config

    def update_notebooklm(
        self,
        api_key: str | None = None,
        enabled: bool | None = None,
    ) -> APIConfig:
        """Update NotebookLM configuration."""
        config = self.load_config()
        
        if api_key is not None:
            config.notebooklm.api_key = api_key
        if enabled is not None:
            config.notebooklm.enabled = enabled

        self.save_config(config)
        return config

    def set_default_provider(self, provider_id: str) -> APIConfig:
        """Set the default LLM provider."""
        config = self.load_config()
        config.default_provider = provider_id
        self.save_config(config)
        return config

    def get_active_providers(self) -> list[LLMProviderConfig]:
        """Get list of enabled providers."""
        config = self.load_config()
        return [p for p in config.providers if p.enabled]

    def get_notebooklm_config(self) -> NotebookLMConfig:
        """Get NotebookLM configuration."""
        config = self.load_config()
        return config.notebooklm

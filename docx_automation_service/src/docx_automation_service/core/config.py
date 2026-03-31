from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DOCX_AUTOMATION_")

    host: str = "0.0.0.0"
    port: int = 8096
    workdir: Path = Path(".runtime")

    similarity_threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    aigc_threshold: float = Field(default=0.2, ge=0.0, le=1.0)

    # --- Layer 2: SiliconFlow / DeepSeek rewriter -----------------------
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    # Default to DeepSeek-V3 for superior academic reasoning at low cost.
    # Switch to "deepseek-ai/DeepSeek-R1" for stronger reasoning tasks.
    siliconflow_model: str = "deepseek-ai/DeepSeek-V3"
    siliconflow_timeout_seconds: float = 90.0
    siliconflow_max_retries: int = 2
    siliconflow_retry_backoff_seconds: float = 1.5

    # --- Layer 1: Azure Translator back-translation ----------------------
    # Endpoint example: https://api.cognitive.microsofttranslator.com
    azure_translator_key: str = ""
    azure_translator_endpoint: str = "https://api.cognitive.microsofttranslator.com"
    # Required for multi-service/regional resources. Optional for global resources.
    azure_translator_region: str = ""
    # When enabled, a configured translator key must include region.
    azure_translator_require_region: bool = True
    # Translation chain key.  Supported values:
    #   "zh-de-en-zh"  – Chinese → German → English → Chinese (default)
    #   "zh-ja-en-zh"  – Chinese → Japanese → English → Chinese
    translation_chain: str = "zh-de-en-zh"
    # Source language used by the first translation hop.
    translation_source_lang: Literal["zh-Hans", "zh-Hant"] = "zh-Hans"

    # --- Layer 3: Burstiness injection ----------------------------------
    # Minimum consecutive long sentences before a short sentence is injected.
    burstiness_min_long_run: int = Field(default=3, ge=1)
    # Burstiness score threshold below which injection is applied (0–1).
    burstiness_injection_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    # Language for burstiness injection phrase bank ("zh" or "en").
    # Defaults to "zh" as this tool targets Chinese academic papers.
    burstiness_lang: str = "zh"

    # --- Rewrite safety/performance controls -----------------------------
    rewrite_chunk_target_chars: int = Field(default=320, ge=120)
    rewrite_chunk_max_chars: int = Field(default=520, ge=180)
    rewrite_skip_heading_chunks: bool = True
    sanitize_model_output: bool = True
    # Deep rewrite can process all chunks (not only flagged) to avoid partial style drift.
    deep_rewrite_process_all_chunks: bool = True
    # If rewritten text is too similar, trigger one stronger retry.
    rewrite_retry_on_low_change: bool = True
    rewrite_min_change_ratio: float = Field(default=0.10, ge=0.0, le=1.0)

    cors_origins: str = "*"
    log_level: str = "INFO"
    log_exception_stack: bool = False

    @model_validator(mode="after")
    def validate_azure_translator_config(self) -> "Settings":
        key = self.azure_translator_key.strip()
        endpoint = self.azure_translator_endpoint.strip()
        region = self.azure_translator_region.strip()

        # Allow disabling Layer 1 by leaving all Azure credentials empty.
        if not key and not region:
            return self

        if not key:
            raise ValueError("azure_translator_region is set but azure_translator_key is empty")

        if not endpoint:
            raise ValueError("azure_translator_endpoint must not be empty when azure_translator_key is set")

        if self.azure_translator_require_region and not region:
            raise ValueError(
                "azure_translator_require_region=true requires azure_translator_region when azure_translator_key is set"
            )

        return self


settings = Settings()

from pathlib import Path

from pydantic import Field
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

    # --- Layer 1: DeepL back-translation --------------------------------
    # Free-tier endpoint: https://api-free.deepl.com/v2
    # Paid-tier endpoint: https://api.deepl.com/v2
    deepl_api_key: str = ""
    deepl_base_url: str = "https://api-free.deepl.com/v2"
    # Translation chain key.  Supported values:
    #   "zh-de-en-zh"  – Chinese → German → English → Chinese (default)
    #   "zh-ja-en-zh"  – Chinese → Japanese → English → Chinese
    translation_chain: str = "zh-de-en-zh"

    # --- Layer 3: Burstiness injection ----------------------------------
    # Minimum consecutive long sentences before a short sentence is injected.
    burstiness_min_long_run: int = Field(default=3, ge=1)
    # Burstiness score threshold below which injection is applied (0–1).
    burstiness_injection_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    # Language for burstiness injection phrase bank ("zh" or "en").
    # Defaults to "zh" as this tool targets Chinese academic papers.
    burstiness_lang: str = "zh"

    cors_origins: str = "*"
    log_level: str = "INFO"


settings = Settings()

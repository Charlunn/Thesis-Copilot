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

    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "Qwen/Qwen2.5-72B-Instruct"
    siliconflow_timeout_seconds: float = 90.0
    siliconflow_max_retries: int = 2
    siliconflow_retry_backoff_seconds: float = 1.5

    cors_origins: str = "*"
    log_level: str = "INFO"


settings = Settings()

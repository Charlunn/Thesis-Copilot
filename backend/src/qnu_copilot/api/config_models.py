from __future__ import annotations

from pydantic import BaseModel, Field


class LLMProviderConfigResponse(BaseModel):
    """Response model for a single LLM provider."""
    provider_id: str
    name: str
    api_type: str
    base_url: str | None = None
    model: str
    enabled: bool


class NotebookLMConfigResponse(BaseModel):
    """Response model for NotebookLM configuration."""
    api_key: str = ""  # Masked in responses
    enabled: bool
    model: str = "notebooklm"


class APIConfigResponse(BaseModel):
    """Response model for API configuration."""
    providers: list[LLMProviderConfigResponse]
    notebooklm: NotebookLMConfigResponse
    default_provider: str
    schema_version: str


class UpdateProviderRequest(BaseModel):
    """Request model for updating a provider."""
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    enabled: bool | None = None


class UpdateNotebookLMRequest(BaseModel):
    """Request model for updating NotebookLM configuration."""
    api_key: str | None = None
    enabled: bool | None = None


class SetDefaultProviderRequest(BaseModel):
    """Request model for setting default provider."""
    provider_id: str


class ProviderStatusResponse(BaseModel):
    """Response model for provider status check."""
    provider_id: str
    name: str
    configured: bool
    has_api_key: bool
    status: str  # configured, missing_key, disabled

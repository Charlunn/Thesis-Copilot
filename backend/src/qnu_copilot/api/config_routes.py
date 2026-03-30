from __future__ import annotations

from pathlib import Path

from qnu_copilot.api.config_models import (
    APIConfigResponse,
    LLMProviderConfigResponse,
    NotebookLMConfigResponse,
    ProviderStatusResponse,
    SetDefaultProviderRequest,
    UpdateNotebookLMRequest,
    UpdateProviderRequest,
)
from qnu_copilot.domain.config import APIConfigService


def create_config_router(data_root: Path) -> APIRouter:
    """Create configuration router with API config endpoints."""
    from fastapi import APIRouter
    
    router = APIRouter()
    config_service = APIConfigService(data_root)

    def _to_response(config) -> APIConfigResponse:
        """Convert config to response model."""
        return APIConfigResponse(
            providers=[
                LLMProviderConfigResponse(
                    provider_id=p.provider_id,
                    name=p.name,
                    api_type=p.api_type,
                    base_url=p.base_url,
                    model=p.model,
                    enabled=p.enabled,
                )
                for p in config.providers
            ],
            notebooklm=NotebookLMConfigResponse(
                api_key="***" if config.notebooklm.api_key else "",
                enabled=config.notebooklm.enabled,
                model=config.notebooklm.model,
            ),
            default_provider=config.default_provider,
            schema_version=config.schema_version,
        )

    @router.get("/config", response_model=APIConfigResponse)
    def get_config() -> APIConfigResponse:
        """Get current API configuration."""
        config = config_service.get_config()
        return _to_response(config)

    @router.put("/config/providers/{provider_id}", response_model=APIConfigResponse)
    def update_provider(
        provider_id: str,
        request: UpdateProviderRequest,
    ) -> APIConfigResponse:
        """Update a specific LLM provider configuration."""
        config = config_service.update_provider(
            provider_id=provider_id,
            api_key=request.api_key,
            model=request.model,
            base_url=request.base_url,
            enabled=request.enabled,
        )
        return _to_response(config)

    @router.put("/config/notebooklm", response_model=APIConfigResponse)
    def update_notebooklm(
        request: UpdateNotebookLMRequest,
    ) -> APIConfigResponse:
        """Update NotebookLM configuration."""
        config = config_service.update_notebooklm(
            api_key=request.api_key,
            enabled=request.enabled,
        )
        return _to_response(config)

    @router.put("/config/default", response_model=APIConfigResponse)
    def set_default_provider(
        request: SetDefaultProviderRequest,
    ) -> APIConfigResponse:
        """Set the default LLM provider."""
        config = config_service.set_default_provider(request.provider_id)
        return _to_response(config)

    @router.get("/config/providers/{provider_id}/status", response_model=ProviderStatusResponse)
    def get_provider_status(provider_id: str) -> ProviderStatusResponse:
        """Get the status of a specific provider."""
        config = config_service.get_config()
        
        # Check NotebookLM separately
        if provider_id == "notebooklm":
            nl_config = config.notebooklm
            return ProviderStatusResponse(
                provider_id="notebooklm",
                name="Google NotebookLM",
                configured=nl_config.enabled and bool(nl_config.api_key),
                has_api_key=bool(nl_config.api_key),
                status="configured" if (nl_config.enabled and nl_config.api_key) else "missing_key" if nl_config.enabled else "disabled",
            )
        
        # Find provider
        for provider in config.providers:
            if provider.provider_id == provider_id:
                has_key = bool(provider.api_key)
                return ProviderStatusResponse(
                    provider_id=provider.provider_id,
                    name=provider.name,
                    configured=provider.enabled and has_key,
                    has_api_key=has_key,
                    status="configured" if (provider.enabled and has_key) else "missing_key" if provider.enabled else "disabled",
                )
        
        # Provider not found
        return ProviderStatusResponse(
            provider_id=provider_id,
            name="Unknown",
            configured=False,
            has_api_key=False,
            status="not_found",
        )

    @router.get("/config/providers", response_model=list[ProviderStatusResponse])
    def list_provider_status() -> list[ProviderStatusResponse]:
        """Get status of all providers."""
        config = config_service.get_config()
        statuses = []
        
        # Add NotebookLM
        nl_config = config.notebooklm
        statuses.append(ProviderStatusResponse(
            provider_id="notebooklm",
            name="Google NotebookLM",
            configured=nl_config.enabled and bool(nl_config.api_key),
            has_api_key=bool(nl_config.api_key),
            status="configured" if (nl_config.enabled and nl_config.api_key) else "missing_key" if nl_config.enabled else "disabled",
        ))
        
        # Add other providers
        for provider in config.providers:
            has_key = bool(provider.api_key)
            statuses.append(ProviderStatusResponse(
                provider_id=provider.provider_id,
                name=provider.name,
                configured=provider.enabled and has_key,
                has_api_key=has_key,
                status="configured" if (provider.enabled and has_key) else "missing_key" if provider.enabled else "disabled",
            ))
        
        return statuses

    return router

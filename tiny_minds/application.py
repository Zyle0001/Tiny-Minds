from __future__ import annotations

from pathlib import Path
from typing import Callable

from .contracts import PipelineResult, RunRequest
from .builtins import register_core
from .engine import PipelineApplication
from .extensions import discover_capabilities, discover_integrations, discover_provider_factories
from .manifest import PipelineManifest, load_manifest
from .providers import ProviderRegistry, RuntimeConfig
from .registry import CapabilityRegistry


def build_registry(integrations: list[str] | None = None, *, extension_allowlist: list[str] | None = None) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    register_core(registry)
    for integration in integrations or []:
        if integration == "workspace-memory":
            try:
                from .integrations.workspace_memory import register_workspace_memory
            except ModuleNotFoundError as exc:
                raise ValueError(
                    "The workspace-memory integration is unavailable; install the 'workspace-memory' extra"
                ) from exc
            register_workspace_memory(registry)
        elif integration == "generic-workspace":
            from .integrations.generic import register_generic
            register_generic(registry)
        else:
            extensions = discover_integrations(extension_allowlist or integrations or [])
            try:
                extensions[integration].register(registry)
            except KeyError as exc:
                raise ValueError(f"Unknown or non-allowlisted integration '{integration}'") from exc
    for capability, extension in discover_capabilities(extension_allowlist or {}).items():
        registry.register(capability, extension.factory)
    return registry


def build_integration_providers(
    integrations: list[str], workspace: Path, *, record_telemetry: bool = False
) -> ProviderRegistry:
    providers = ProviderRegistry()
    if "workspace-memory" in integrations:
        from .integrations.foundry import FoundryEmbeddingProvider
        providers.register("embeddings", FoundryEmbeddingProvider(workspace, record_telemetry))
    return providers


def build_configured_providers(
    config: RuntimeConfig | None, *, workspace: Path | None = None, record_telemetry: bool = False
) -> ProviderRegistry:
    providers = ProviderRegistry()
    if config is None:
        return providers
    factories = discover_provider_factories(
        [provider.implementation for provider in config.providers if provider.implementation not in {"foundry"}]
    )
    for provider_config in config.providers:
        if provider_config.implementation == "foundry":
            if workspace is None:
                raise ValueError("The Foundry adapter requires an explicit workspace root")
            from .integrations.foundry import (
                FoundryClassificationProvider, FoundryEmbeddingProvider, FoundryNliProvider, FoundryRerankingProvider,
            )
            model_id = provider_config.model_id or {
                "embeddings": "all-MiniLM-L6-v2", "reranker": "ms-marco-MiniLM-L6-v2",
                "nli": "nli-MiniLM2-L6-H768", "classification": "nli-MiniLM2-L6-H768",
            }.get(provider_config.kind, "")
            constructors = {
                "embeddings": lambda: FoundryEmbeddingProvider(workspace, record_telemetry),
                "reranker": lambda: FoundryRerankingProvider(workspace, model_id, record_telemetry),
                "nli": lambda: FoundryNliProvider(workspace, model_id, record_telemetry),
                "classification": lambda: FoundryClassificationProvider(workspace, model_id, record_telemetry),
            }
            try:
                provider = constructors[provider_config.kind]()
            except KeyError as exc:
                raise ValueError(f"Foundry does not provide configured kind '{provider_config.kind}'") from exc
        else:
            try:
                provider = factories[provider_config.implementation].factory(provider_config)
            except KeyError as exc:
                raise ValueError(f"Unknown provider implementation '{provider_config.implementation}'") from exc
        providers.register(provider_config.id, provider)
    return providers


def execute_pipeline(
    manifest: PipelineManifest | Path,
    request: RunRequest | dict,
    workspace: Path,
    providers: ProviderRegistry | None = None,
    extension_allowlist: list[str] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> PipelineResult:
    """Stable application seam for the CLI and a future MCP adapter."""
    loaded = load_manifest(manifest) if isinstance(manifest, Path) else manifest
    cooked_request = request if isinstance(request, RunRequest) else RunRequest.model_validate(request)
    return PipelineApplication(build_registry(loaded.integrations, extension_allowlist=extension_allowlist), providers).run(
        loaded, cooked_request, workspace, cancel_check=cancel_check
    )

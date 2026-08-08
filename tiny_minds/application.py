from __future__ import annotations

from pathlib import Path

from .contracts import PipelineResult, RunRequest
from .builtins import register_core
from .engine import PipelineApplication
from .manifest import PipelineManifest, load_manifest
from .providers import ProviderRegistry
from .registry import CapabilityRegistry


def build_registry(integrations: list[str] | None = None) -> CapabilityRegistry:
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
        else:
            raise ValueError(f"Unknown integration '{integration}'")
    return registry


def build_integration_providers(
    integrations: list[str], workspace: Path, *, record_telemetry: bool = False
) -> ProviderRegistry:
    providers = ProviderRegistry()
    if "workspace-memory" in integrations:
        from .integrations.foundry import FoundryEmbeddingProvider
        providers.register("embeddings", FoundryEmbeddingProvider(workspace, record_telemetry))
    return providers


def execute_pipeline(
    manifest: PipelineManifest | Path,
    request: RunRequest | dict,
    workspace: Path,
    providers: ProviderRegistry | None = None,
) -> PipelineResult:
    """Stable application seam for the CLI and a future MCP adapter."""
    loaded = load_manifest(manifest) if isinstance(manifest, Path) else manifest
    cooked_request = request if isinstance(request, RunRequest) else RunRequest.model_validate(request)
    return PipelineApplication(build_registry(loaded.integrations), providers).run(loaded, cooked_request, workspace)

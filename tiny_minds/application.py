from __future__ import annotations

from pathlib import Path

from .contracts import PipelineResult, RunRequest
from .engine import PipelineApplication
from .integrations.workspace_memory import register_workspace_memory
from .manifest import PipelineManifest, load_manifest
from .registry import CapabilityRegistry


def build_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    register_workspace_memory(registry)
    return registry


def execute_pipeline(
    manifest: PipelineManifest | Path,
    request: RunRequest | dict,
    workspace: Path,
) -> PipelineResult:
    """Stable application seam for the CLI and a future MCP adapter."""
    loaded = load_manifest(manifest) if isinstance(manifest, Path) else manifest
    cooked_request = request if isinstance(request, RunRequest) else RunRequest.model_validate(request)
    return PipelineApplication(build_registry()).run(loaded, cooked_request, workspace)

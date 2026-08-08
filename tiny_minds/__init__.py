"""Tiny Minds cognitive machinery runtime."""

from .contracts import (
    ArtifactRef, BoundedContextPacket, ChangeSet, ChunkRef, PipelineResult,
    PrimitiveResult, RankedCandidate, RunRequest, WorkspaceScope,
)
from .engine import PipelineApplication
from .providers import ProviderConfig, ProviderRegistry, RuntimeConfig

__all__ = [
    "ArtifactRef", "BoundedContextPacket", "ChangeSet", "ChunkRef", "PipelineApplication",
    "PipelineResult", "PrimitiveResult", "ProviderConfig", "ProviderRegistry", "RankedCandidate",
    "RunRequest", "RuntimeConfig", "WorkspaceScope",
]

__version__ = "0.2.0"

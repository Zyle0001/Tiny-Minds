from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = 1


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceReference(ContractModel):
    path: str
    heading: str | None = None
    chunk_id: str | None = None
    content_sha256: str | None = None
    excerpt: str | None = Field(default=None, max_length=240)


class Provenance(ContractModel):
    implementation: str
    version: str
    model_id: str | None = None
    model_revision: str | None = None
    model_sha256: str | None = None
    verification: list[dict[str, Any]] = Field(default_factory=list)


class PrimitiveMetrics(ContractModel):
    duration_ms: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    candidate_count: int = 0


class PrimitiveResult(ContractModel):
    capability: str
    version: str
    status: Literal["success", "skipped", "unavailable", "error"]
    data: dict[str, Any] = Field(default_factory=dict)
    scores: dict[str, float] = Field(default_factory=dict)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    provenance: Provenance
    metrics: PrimitiveMetrics = Field(default_factory=PrimitiveMetrics)
    diagnostics: list[str] = Field(default_factory=list)
    remediation: str | None = None


class PipelineIdentity(ContractModel):
    id: str
    version: str


class PipelineResult(ContractModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    run_id: str
    pipeline: PipelineIdentity
    status: Literal["success", "partial", "error"]
    disposition: Literal["resolved", "review", "escalate"]
    primitives: dict[str, PrimitiveResult]
    evidence: list[EvidenceReference] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class RunRequest(ContractModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    inputs: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    debug: bool = False

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

import yaml
from pydantic import Field, field_validator

from .contracts import ContractModel, EXTENSION_API_VERSION


class ProviderUnavailable(RuntimeError):
    def __init__(self, message: str, remediation: str | None = None) -> None:
        super().__init__(message)
        self.remediation = remediation


class EmbeddingRequest(ContractModel):
    texts: list[str]
    model_id: str | None = None


class EmbeddingResponse(ContractModel):
    vectors: list[list[float]]
    model: dict[str, Any] = Field(default_factory=dict)


class RerankRequest(ContractModel):
    query: str
    documents: list[str]
    model_id: str | None = None


class RerankResponse(ContractModel):
    scores: list[float]
    model: dict[str, Any] = Field(default_factory=dict)


class NliPair(ContractModel):
    premise: str
    hypothesis: str


class NliRequest(ContractModel):
    pairs: list[NliPair]
    model_id: str | None = None


class NliScores(ContractModel):
    contradiction: float
    entailment: float
    neutral: float


class NliResponse(ContractModel):
    scores: list[NliScores]
    model: dict[str, Any] = Field(default_factory=dict)


class ClassificationRequest(ContractModel):
    texts: list[str]
    labels: list[str]
    model_id: str | None = None


class ClassificationResponse(ContractModel):
    scores: list[dict[str, float]]
    model: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class EmbeddingProvider(Protocol):
    provider_id: str

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...


@runtime_checkable
class RerankingProvider(Protocol):
    provider_id: str

    def rerank(self, request: RerankRequest) -> RerankResponse: ...


@runtime_checkable
class NliProvider(Protocol):
    provider_id: str

    def nli(self, request: NliRequest) -> NliResponse: ...


@runtime_checkable
class ClassificationProvider(Protocol):
    provider_id: str

    def classify(self, request: ClassificationRequest) -> ClassificationResponse: ...


class ProviderConfig(ContractModel):
    schema_version: Literal[1] = EXTENSION_API_VERSION
    id: str
    kind: Literal["embeddings", "reranker", "nli", "classification", "multi"]
    implementation: str
    endpoint: str | None = None
    model_id: str | None = None
    model_revision: str | None = None
    model_sha256: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    batch_limit: int = Field(default=32, gt=0, le=4096)
    auth_env: str | None = None
    settings: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_not_embed_credentials(cls, value: str | None) -> str | None:
        if value and "://" in value and "@" in value.split("://", 1)[1].split("/", 1)[0]:
            raise ValueError("Provider endpoints must not embed credentials; use auth_env")
        return value

    @field_validator("auth_env")
    @classmethod
    def auth_reference_must_be_environment_name(cls, value: str | None) -> str | None:
        if value and (not value.replace("_", "").isalnum() or value[0].isdigit()):
            raise ValueError("auth_env must name an environment variable")
        return value

    def resolved_auth(self) -> str | None:
        return os.environ.get(self.auth_env) if self.auth_env else None

    def cache_identity(self) -> dict[str, Any]:
        return {
            "provider_id": self.id, "implementation": self.implementation, "kind": self.kind,
            "model_id": self.model_id, "model_revision": self.model_revision,
            "model_sha256": self.model_sha256, "settings": self.settings,
        }


class RuntimeConfig(ContractModel):
    schema_version: Literal[1] = EXTENSION_API_VERSION
    allowed_extensions: list[str] = Field(default_factory=list)
    providers: list[ProviderConfig] = Field(default_factory=list)


def load_runtime_config(path: Path) -> RuntimeConfig:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read Tiny Minds configuration '{path}': {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Tiny Minds configuration must contain a mapping")
    return RuntimeConfig.model_validate(payload)


class ProviderRegistry:
    """Explicit providers. An empty registry is always a valid core configuration."""

    def __init__(self) -> None:
        self._providers: dict[str, object] = {}

    def register(self, provider_id: str, provider: object) -> None:
        if provider_id in self._providers:
            raise ValueError(f"Provider '{provider_id}' is already registered")
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> object | None:
        return self._providers.get(provider_id)

    def require(self, provider_id: str, protocol: type) -> object:
        provider = self.get(provider_id)
        if provider is None:
            raise ProviderUnavailable(f"Provider '{provider_id}' is not configured")
        if not isinstance(provider, protocol):
            raise ProviderUnavailable(f"Provider '{provider_id}' does not implement {protocol.__name__}")
        return provider

    def providers(self) -> list[str]:
        return sorted(self._providers)

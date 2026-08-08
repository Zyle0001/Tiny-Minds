from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..providers import (
    ClassificationRequest, ClassificationResponse, EmbeddingRequest, EmbeddingResponse,
    NliRequest, NliResponse, NliScores, ProviderUnavailable, RerankRequest, RerankResponse,
)


class FoundryEmbeddingProvider:
    """Optional workspace adapter; the provider-neutral core never imports this module."""

    provider_id = "embeddings"

    def __init__(self, workspace: Path, record_telemetry: bool = False) -> None:
        self.workspace = workspace.resolve()
        self.record_telemetry = record_telemetry

    def _adapter(self, model_id: str) -> dict[str, Any]:
        path = (
            self.workspace / "Tools" / "foundry-local-runtime" / "ONNX host service"
            / "models" / model_id / "adapter.json"
        )
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderUnavailable(
                f"Foundry model '{model_id}' is not installed or has invalid metadata",
                "Install the model explicitly in the configured Foundry runtime",
            ) from exc
        return metadata

    def cache_identity(self, model_id: str | None = None) -> dict[str, Any]:
        selected = model_id or "all-MiniLM-L6-v2"
        return {"provider_id": self.provider_id, "implementation": "foundry", **self._adapter(selected)}

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model_id = request.model_id or "all-MiniLM-L6-v2"
        adapter = self._adapter(model_id)
        metadata = {
            "model_id": model_id,
            "revision": adapter.get("revision"),
            "model_sha256": adapter.get("model_sha256"),
            "pooling": adapter.get("pooling"),
            "normalize": adapter.get("normalize"),
            "max_length": adapter.get("max_length"),
        }
        try:
            from ..services.foundry import FoundryManager, FoundryServiceError
            vectors, service = FoundryManager(self.workspace, self.record_telemetry).embed(
                request.texts, model_id, 8123
            )
        except (ImportError, FoundryServiceError) as exc:
            raise ProviderUnavailable(
                f"Foundry embedding provider is unavailable: {exc}",
                "Install the 'foundry' extra and configure a compatible Foundry runtime, or keep the node optional",
            ) from exc
        metadata["service"] = service
        return EmbeddingResponse(vectors=vectors, model=metadata)


class _FoundrySequenceProvider:
    provider_id = "sequence"

    def __init__(self, workspace: Path, model_id: str, record_telemetry: bool = False) -> None:
        self.workspace = workspace.resolve()
        self.model_id = model_id
        self.record_telemetry = record_telemetry

    def _manager(self):
        try:
            from ..services.foundry import FoundryManager
            return FoundryManager(self.workspace, self.record_telemetry)
        except ImportError as exc:
            raise ProviderUnavailable("Foundry provider extra is unavailable") from exc

    def _model(self, requested: str | None) -> str:
        return requested or self.model_id

    def cache_identity(self, model_id: str | None = None) -> dict[str, Any]:
        selected = self._model(model_id)
        path = self.workspace / "Tools" / "foundry-local-runtime" / "ONNX host service" / "models" / selected / "adapter.json"
        try:
            adapter = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            adapter = {}
        return {
            "provider_id": self.provider_id, "implementation": "foundry", "model_id": selected,
            "model_revision": adapter.get("revision"), "model_sha256": adapter.get("model_sha256"),
            "adapter": {key: adapter.get(key) for key in ("task", "max_length", "labels", "positive_label")},
        }


class FoundryRerankingProvider(_FoundrySequenceProvider):
    provider_id = "reranker"

    def rerank(self, request: RerankRequest) -> RerankResponse:
        try:
            scores, _ = self._manager().rerank(request.query, request.documents, self._model(request.model_id))
        except Exception as exc:
            raise ProviderUnavailable(f"Foundry reranker is unavailable: {exc}") from exc
        return RerankResponse(scores=scores, model={"model_id": self._model(request.model_id)})


class FoundryNliProvider(_FoundrySequenceProvider):
    provider_id = "nli"

    def nli(self, request: NliRequest) -> NliResponse:
        try:
            rows, _ = self._manager().nli([item.model_dump() for item in request.pairs], self._model(request.model_id))
        except Exception as exc:
            raise ProviderUnavailable(f"Foundry NLI provider is unavailable: {exc}") from exc
        return NliResponse(scores=[NliScores.model_validate(item) for item in rows], model={"model_id": self._model(request.model_id)})


class FoundryClassificationProvider(_FoundrySequenceProvider):
    provider_id = "classification"

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        try:
            rows, _ = self._manager().classify(request.texts, request.labels, self._model(request.model_id))
        except Exception as exc:
            raise ProviderUnavailable(f"Foundry classifier is unavailable: {exc}") from exc
        return ClassificationResponse(scores=rows, model={"model_id": self._model(request.model_id)})

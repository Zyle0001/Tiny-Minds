from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..providers import ProviderUnavailable


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

    def invoke(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        model_id = str(payload.get("model_id", "all-MiniLM-L6-v2"))
        adapter = self._adapter(model_id)
        metadata = {
            "model_id": model_id,
            "revision": adapter.get("revision"),
            "model_sha256": adapter.get("model_sha256"),
            "pooling": adapter.get("pooling"),
            "normalize": adapter.get("normalize"),
            "max_length": adapter.get("max_length"),
        }
        if operation == "describe":
            return metadata
        if operation != "embed":
            raise ProviderUnavailable(f"Foundry embedding provider does not support operation '{operation}'")
        texts = payload.get("texts")
        if not isinstance(texts, list) or not all(isinstance(item, str) for item in texts):
            raise ValueError("Embedding provider requires a list of text strings")
        try:
            from ..services.foundry import FoundryManager, FoundryServiceError
            vectors, service = FoundryManager(self.workspace, self.record_telemetry).embed(
                texts, model_id, int(payload.get("preferred_port", 8123))
            )
        except (ImportError, FoundryServiceError) as exc:
            raise ProviderUnavailable(
                f"Foundry embedding provider is unavailable: {exc}",
                "Install the 'foundry' extra and configure a compatible Foundry runtime, or keep the node optional",
            ) from exc
        return {"vectors": vectors, "model": metadata, "service": service}

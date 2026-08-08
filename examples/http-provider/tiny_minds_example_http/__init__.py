from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from tiny_minds.extensions import ProviderExtension
from tiny_minds.providers import (
    ClassificationRequest, ClassificationResponse, EmbeddingRequest, EmbeddingResponse,
    NliRequest, NliResponse, ProviderConfig, ProviderUnavailable, RerankRequest, RerankResponse,
)


class HttpCognitiveProvider:
    def __init__(self, config: ProviderConfig) -> None:
        if not config.endpoint:
            raise ValueError("example-http requires an endpoint")
        self.provider_id = config.id
        self.config = config

    def cache_identity(self, model_id: str | None = None) -> dict[str, Any]:
        identity = self.config.cache_identity()
        if model_id:
            identity["model_id"] = model_id
        return identity

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.config.endpoint.rstrip('/')}/{path.lstrip('/')}",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"},
        )
        auth = self.config.resolved_auth()
        if auth:
            request.add_header("Authorization", f"Bearer {auth}")
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderUnavailable(f"HTTP cognitive provider is unavailable: {exc}") from exc
        if not isinstance(result, dict):
            raise ProviderUnavailable("HTTP cognitive provider returned a non-object response")
        return result

    def _validated(self, model: type, path: str, payload: dict[str, Any]):
        try:
            return model.model_validate(self._post(path, payload))
        except ValueError as exc:
            raise ProviderUnavailable(f"HTTP cognitive provider returned an invalid {path} response: {exc}") from exc

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return self._validated(EmbeddingResponse, "embeddings", request.model_dump())

    def rerank(self, request: RerankRequest) -> RerankResponse:
        return self._validated(RerankResponse, "rerank", request.model_dump())

    def nli(self, request: NliRequest) -> NliResponse:
        return self._validated(NliResponse, "nli", request.model_dump())

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        return self._validated(ClassificationResponse, "classify", request.model_dump())


def extension() -> ProviderExtension:
    return ProviderExtension("example-http", 1, HttpCognitiveProvider)

from __future__ import annotations

from typing import Any, Protocol


class Provider(Protocol):
    provider_id: str

    def invoke(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class ProviderUnavailable(RuntimeError):
    def __init__(self, message: str, remediation: str | None = None) -> None:
        super().__init__(message)
        self.remediation = remediation


class ProviderRegistry:
    """Explicit runtime providers; an empty registry is a valid core configuration."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider_id: str, provider: Provider) -> None:
        if provider_id in self._providers:
            raise ValueError(f"Provider '{provider_id}' is already registered")
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> Provider | None:
        return self._providers.get(provider_id)

    def providers(self) -> list[str]:
        return sorted(self._providers)

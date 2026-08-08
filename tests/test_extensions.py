from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path

import pytest

from tiny_minds.extensions import (
    CapabilityExtension, DoctorCheckExtension, IntegrationExtension, ProviderExtension, ServiceControlExtension,
    discover_capabilities, discover_doctor_checks, discover_integrations, discover_provider_factories,
    discover_service_controls,
)
from tiny_minds.providers import EmbeddingRequest, ProviderConfig, ProviderUnavailable, RuntimeConfig


@dataclass
class Entry:
    name: str
    value: object

    def load(self):
        return self.value


def test_extension_allowlist_and_version_negotiation() -> None:
    good = Entry("sample", IntegrationExtension("sample", 1, lambda registry: None))
    ignored = Entry("ignored", IntegrationExtension("ignored", 1, lambda registry: None))
    assert list(discover_integrations(["sample"], entries=[good, ignored])) == ["sample"]
    bad = Entry("sample", IntegrationExtension("sample", 99, lambda registry: None))
    with pytest.raises(ValueError, match="requires extension API"):
        discover_integrations(["sample"], entries=[bad])


def test_duplicate_provider_entry_points_are_rejected() -> None:
    extension = ProviderExtension("provider", 1, lambda config: object())
    with pytest.raises(ValueError, match="more than once"):
        discover_provider_factories(["provider"], entries=[Entry("provider", extension), Entry("provider", extension)])


def test_provider_configuration_never_contains_resolved_secret(monkeypatch) -> None:
    monkeypatch.setenv("TINY_TEST_SECRET", "do-not-serialize")
    config = RuntimeConfig(providers=[ProviderConfig(
        id="nli", kind="nli", implementation="example-http", endpoint="http://127.0.0.1:1", auth_env="TINY_TEST_SECRET"
    )])
    assert config.providers[0].resolved_auth() == "do-not-serialize"
    assert "do-not-serialize" not in config.model_dump_json()


def test_all_extension_surfaces_are_versioned_and_allowlisted() -> None:
    capability = CapabilityExtension("sample.capability", 1, lambda: object())
    doctor = DoctorCheckExtension("sample-doctor", 1, lambda context: {"healthy": True})
    service = ServiceControlExtension("sample-service", 1, lambda context: object())
    assert "sample.capability" in discover_capabilities(["sample.capability"], entries=[Entry("sample.capability", capability)])
    assert "sample-doctor" in discover_doctor_checks(["sample-doctor"], entries=[Entry("sample-doctor", doctor)])
    assert "sample-service" in discover_service_controls(["sample-service"], entries=[Entry("sample-service", service)])


def test_example_http_provider_turns_malformed_responses_into_unavailability(monkeypatch) -> None:
    path = Path(__file__).parents[1] / "examples" / "http-provider" / "tiny_minds_example_http" / "__init__.py"
    spec = importlib.util.spec_from_file_location("test_http_provider", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    provider = module.HttpCognitiveProvider(ProviderConfig(
        id="embeddings", kind="embeddings", implementation="example-http", endpoint="http://127.0.0.1:1"
    ))
    monkeypatch.setattr(provider, "_post", lambda path, payload: {"unexpected": True})
    with pytest.raises(ProviderUnavailable, match="invalid embeddings response"):
        provider.embed(EmbeddingRequest(texts=["test"]))

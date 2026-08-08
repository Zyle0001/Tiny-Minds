from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Any, Callable, Iterable

from .contracts import EXTENSION_API_VERSION
from .registry import CapabilityRegistry


IntegrationRegister = Callable[[CapabilityRegistry], None]


@dataclass(frozen=True)
class IntegrationExtension:
    integration_id: str
    api_version: int
    register: IntegrationRegister


@dataclass(frozen=True)
class ProviderExtension:
    implementation_id: str
    api_version: int
    factory: Callable[[Any], object]


@dataclass(frozen=True)
class CapabilityExtension:
    capability_id: str
    api_version: int
    factory: Callable[[], object]


@dataclass(frozen=True)
class DoctorCheckExtension:
    check_id: str
    api_version: int
    check: Callable[[Any], dict[str, Any]]


@dataclass(frozen=True)
class ServiceControlExtension:
    service_id: str
    api_version: int
    factory: Callable[[Any], object]


def discover_integrations(
    allowlist: Iterable[str], *, entries: Iterable[metadata.EntryPoint] | None = None
) -> dict[str, IntegrationExtension]:
    allowed = set(allowlist)
    if entries is None:
        selected = metadata.entry_points()
        entries = selected.select(group="tiny_minds.integrations") if hasattr(selected, "select") else selected.get("tiny_minds.integrations", [])
    discovered: dict[str, IntegrationExtension] = {}
    for entry in entries:
        if entry.name not in allowed:
            continue
        loaded = entry.load()
        extension = loaded() if callable(loaded) and not isinstance(loaded, IntegrationExtension) else loaded
        if not isinstance(extension, IntegrationExtension):
            raise ValueError(f"Integration entry point '{entry.name}' returned an invalid extension")
        if extension.integration_id != entry.name:
            raise ValueError(f"Integration entry point '{entry.name}' declared ID '{extension.integration_id}'")
        if extension.api_version != EXTENSION_API_VERSION:
            raise ValueError(
                f"Integration '{entry.name}' requires extension API {extension.api_version}; runtime supports {EXTENSION_API_VERSION}"
            )
        if entry.name in discovered:
            raise ValueError(f"Integration '{entry.name}' was discovered more than once")
        discovered[entry.name] = extension
    return discovered


def discover_provider_factories(
    allowlist: Iterable[str], *, entries: Iterable[metadata.EntryPoint] | None = None
) -> dict[str, ProviderExtension]:
    allowed = set(allowlist)
    if entries is None:
        selected = metadata.entry_points()
        entries = selected.select(group="tiny_minds.providers") if hasattr(selected, "select") else selected.get("tiny_minds.providers", [])
    discovered: dict[str, ProviderExtension] = {}
    for entry in entries:
        if entry.name not in allowed:
            continue
        loaded = entry.load()
        extension = loaded() if callable(loaded) and not isinstance(loaded, ProviderExtension) else loaded
        if not isinstance(extension, ProviderExtension) or extension.implementation_id != entry.name:
            raise ValueError(f"Provider entry point '{entry.name}' returned an invalid extension")
        if extension.api_version != EXTENSION_API_VERSION:
            raise ValueError(f"Provider '{entry.name}' uses incompatible extension API {extension.api_version}")
        if entry.name in discovered:
            raise ValueError(f"Provider implementation '{entry.name}' was discovered more than once")
        discovered[entry.name] = extension
    return discovered


def _discover_typed(group: str, allowlist: Iterable[str], expected: type, id_field: str,
                    entries: Iterable[metadata.EntryPoint] | None = None) -> dict[str, Any]:
    allowed = set(allowlist)
    if entries is None:
        selected = metadata.entry_points()
        entries = selected.select(group=group) if hasattr(selected, "select") else selected.get(group, [])
    discovered = {}
    for entry in entries:
        if entry.name not in allowed:
            continue
        loaded = entry.load()
        extension = loaded() if callable(loaded) and not isinstance(loaded, expected) else loaded
        if not isinstance(extension, expected) or getattr(extension, id_field) != entry.name:
            raise ValueError(f"Entry point '{entry.name}' in '{group}' returned an invalid extension")
        if extension.api_version != EXTENSION_API_VERSION:
            raise ValueError(f"Extension '{entry.name}' in '{group}' uses incompatible API {extension.api_version}")
        if entry.name in discovered:
            raise ValueError(f"Extension '{entry.name}' in '{group}' was discovered more than once")
        discovered[entry.name] = extension
    return discovered


def discover_capabilities(allowlist: Iterable[str], *, entries=None) -> dict[str, CapabilityExtension]:
    return _discover_typed("tiny_minds.capabilities", allowlist, CapabilityExtension, "capability_id", entries)


def discover_doctor_checks(allowlist: Iterable[str], *, entries=None) -> dict[str, DoctorCheckExtension]:
    return _discover_typed("tiny_minds.doctor_checks", allowlist, DoctorCheckExtension, "check_id", entries)


def discover_service_controls(allowlist: Iterable[str], *, entries=None) -> dict[str, ServiceControlExtension]:
    return _discover_typed("tiny_minds.service_controls", allowlist, ServiceControlExtension, "service_id", entries)

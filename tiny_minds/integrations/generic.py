from __future__ import annotations

from ..extensions import IntegrationExtension
from ..registry import CapabilityRegistry
from .generic_capabilities import register_generic_capabilities


def extension() -> IntegrationExtension:
    return IntegrationExtension("generic-workspace", 1, register_generic_capabilities)


def register_generic(registry: CapabilityRegistry) -> None:
    register_generic_capabilities(registry)

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .contracts import PrimitiveResult


class Primitive(Protocol):
    capability: str
    version: str

    def execute(self, context: object, config: dict, dependencies: dict[str, PrimitiveResult]) -> PrimitiveResult: ...


Factory = Callable[[], Primitive]


class CapabilityRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Factory] = {}

    def register(self, capability: str, factory: Factory) -> None:
        if capability in self._factories:
            raise ValueError(f"Capability '{capability}' is already registered")
        self._factories[capability] = factory

    def create(self, capability: str) -> Primitive:
        try:
            return self._factories[capability]()
        except KeyError as exc:
            raise KeyError(f"Unknown capability '{capability}'") from exc

    def capabilities(self) -> list[str]:
        return sorted(self._factories)

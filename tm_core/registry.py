"""Mind registry for dependency injection."""
from __future__ import annotations

from typing import Dict, Iterable, Iterator, Tuple

from .base_mind import BaseMind


class MindRegistry:
    """A lightweight registry mapping mind names to instances."""

    def __init__(self) -> None:
        self._minds: Dict[str, BaseMind] = {}

    def register(self, mind: BaseMind) -> None:
        """Register a mind instance by its `name` attribute."""

        if mind.name in self._minds:
            raise ValueError(f"Mind '{mind.name}' is already registered.")
        self._minds[mind.name] = mind

    def get(self, name: str) -> BaseMind:
        """Retrieve a mind by name."""

        try:
            return self._minds[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"Mind '{name}' is not registered.") from exc

    def items(self) -> Iterable[Tuple[str, BaseMind]]:
        return self._minds.items()

    def __contains__(self, name: str) -> bool:
        return name in self._minds

    def __iter__(self) -> Iterator[BaseMind]:
        return iter(self._minds.values())

    def as_dict(self) -> Dict[str, BaseMind]:
        """Return the underlying mapping (copy) for convenience."""

        return dict(self._minds)

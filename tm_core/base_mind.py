"""Core base class for all Minds."""
from __future__ import annotations

import abc
from typing import Dict

from .message_types import MindInput, MindOutput


class BaseMind(abc.ABC):
    """Abstract base class describing the lifecycle of a Mind."""

    name: str
    version: str
    embed_dim: int

    def __init__(self, name: str, version: str, embed_dim: int) -> None:
        self.name = name
        self.version = version
        self.embed_dim = embed_dim

    @abc.abstractmethod
    def load(self, ckpt_path: str) -> None:
        """Load model state from a checkpoint."""

    @abc.abstractmethod
    def save(self, ckpt_path: str) -> None:
        """Persist model state to a checkpoint."""

    @abc.abstractmethod
    def think(self, inp: MindInput) -> MindOutput:
        """Produce a `MindOutput` from the provided `MindInput`."""

    @abc.abstractmethod
    def train_step(self, batch: Dict) -> Dict:
        """Run a single training step and return logged metrics."""

    @abc.abstractmethod
    def visualize(self, logdir: str) -> None:
        """Generate artifacts or plots describing the Mind's state."""

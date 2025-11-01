"""Stub ContextMind maintaining a running state vector."""
from __future__ import annotations

from typing import Dict

import numpy as np

from tm_core.base_mind import BaseMind
from tm_core.message_types import MindInput, MindOutput


class ContextMind(BaseMind):
    def __init__(self, embed_dim: int = 16) -> None:
        super().__init__(name="context", version="0.1.0", embed_dim=embed_dim)
        self._state = np.zeros((embed_dim,), dtype=np.float32)

    def state_vector(self) -> np.ndarray:
        return self._state

    def load(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def save(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def think(self, inp: MindInput) -> MindOutput:
        mind_signals = inp.get("mind_signals", {})
        agg = np.zeros_like(self._state)
        for signal in mind_signals.values():
            vec = signal.get("embedding")
            if isinstance(vec, np.ndarray) and vec.shape == self._state.shape:
                agg += vec
        agg /= max(1, len(mind_signals))
        self._state = 0.8 * self._state + 0.2 * agg
        return MindOutput(
            embedding=self._state,
            confidence=1.0,
            labels={"summary": "stub"},
            suggestions={},
            aux={"mind_count": len(mind_signals)},
        )

    def train_step(self, batch: Dict) -> Dict:
        return {"loss": 0.0}

    def visualize(self, logdir: str) -> None:  # pragma: no cover
        return None

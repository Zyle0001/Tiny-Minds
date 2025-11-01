"""Stub EmpathyMind that mirrors affect signals."""
from __future__ import annotations

from typing import Dict

import numpy as np

from tm_core.base_mind import BaseMind
from tm_core.message_types import MindInput, MindOutput


class EmpathyMind(BaseMind):
    def __init__(self, embed_dim: int = 8) -> None:
        super().__init__(name="empathy", version="0.1.0", embed_dim=embed_dim)

    def load(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def save(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def think(self, inp: MindInput) -> MindOutput:
        affect = inp.get("mind_signals", {}).get("affect", {})
        valence = affect.get("labels", {}).get("valence", 0.0)
        embedding = np.full((self.embed_dim,), float(valence), dtype=np.float32)
        return MindOutput(
            embedding=embedding,
            confidence=float(min(1.0, abs(valence))),
            labels={"mirrored_valence": valence},
            suggestions={"phrase": "I hear you." if valence < 0 else "That's wonderful!"},
            aux={},
        )

    def train_step(self, batch: Dict) -> Dict:
        return {"loss": 0.0}

    def visualize(self, logdir: str) -> None:  # pragma: no cover
        return None

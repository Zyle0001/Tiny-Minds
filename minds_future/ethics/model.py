"""Stub EthicsMind that echoes safe replies."""
from __future__ import annotations

from typing import Dict

import numpy as np

from tm_core.base_mind import BaseMind
from tm_core.message_types import MindInput, MindOutput


class EthicsMind(BaseMind):
    def __init__(self, embed_dim: int = 4) -> None:
        super().__init__(name="ethics", version="0.1.0", embed_dim=embed_dim)

    def load(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def save(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def think(self, inp: MindInput) -> MindOutput:
        text = inp.get("text", "") or ""
        embedding = np.zeros((self.embed_dim,), dtype=np.float32)
        return MindOutput(
            embedding=embedding,
            confidence=1.0,
            labels={"risk": 0.0},
            suggestions={"reply": text},
            aux={},
        )

    def train_step(self, batch: Dict) -> Dict:
        return {"loss": 0.0}

    def visualize(self, logdir: str) -> None:  # pragma: no cover
        return None

"""Stub LogicMind providing pseudo rule evaluation."""
from __future__ import annotations

import hashlib
from typing import Dict

import numpy as np

from tm_core.base_mind import BaseMind
from tm_core.message_types import MindInput, MindOutput


class LogicMind(BaseMind):
    def __init__(self, embed_dim: int = 8) -> None:
        super().__init__(name="logic", version="0.1.0", embed_dim=embed_dim)

    def load(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def save(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def think(self, inp: MindInput) -> MindOutput:
        text = inp.get("text", "") or ""
        digest = hashlib.sha1(text.encode("utf-8")).digest()
        confidence = (digest[0] / 255.0)
        rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))
        embedding = rng.normal(size=self.embed_dim).astype(np.float32)
        relation = ["implication", "contradiction", "comparison"][digest[1] % 3]
        return MindOutput(
            embedding=embedding,
            confidence=float(confidence),
            labels={"relation": relation},
            suggestions={},
            aux={"digest": digest.hex()},
        )

    def train_step(self, batch: Dict) -> Dict:
        return {"loss": 0.0}

    def visualize(self, logdir: str) -> None:  # pragma: no cover
        return None

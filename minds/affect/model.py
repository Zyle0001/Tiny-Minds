"""Stub AffectMind returning deterministic pseudo-random outputs."""
from __future__ import annotations

import hashlib
from typing import Dict

import numpy as np

from tm_core.base_mind import BaseMind
from tm_core.message_types import MindInput, MindOutput


class AffectMind(BaseMind):
    def __init__(self, embed_dim: int = 8) -> None:
        super().__init__(name="affect", version="0.1.0", embed_dim=embed_dim)

    def load(self, ckpt_path: str) -> None:  # pragma: no cover - no-op for stub
        return None

    def save(self, ckpt_path: str) -> None:  # pragma: no cover - no-op for stub
        return None

    def think(self, inp: MindInput) -> MindOutput:
        text = inp.get("text", "") or ""
        seed_bytes = hashlib.sha256(text.encode("utf-8")).digest()
        rng = np.random.default_rng(int.from_bytes(seed_bytes[:8], "little"))
        embedding = rng.normal(size=self.embed_dim).astype(np.float32)
        valence = float(rng.uniform(-1.0, 1.0))
        arousal = float(rng.uniform(0.0, 1.0))
        return MindOutput(
            embedding=embedding,
            confidence=float(abs(valence)),
            labels={"valence": valence, "arousal": arousal},
            suggestions={"tone": "calm" if valence >= 0 else "soothing"},
            aux={"seed": seed_bytes.hex()},
        )

    def train_step(self, batch: Dict) -> Dict:
        return {"loss": 0.0}

    def visualize(self, logdir: str) -> None:  # pragma: no cover - stub
        return None

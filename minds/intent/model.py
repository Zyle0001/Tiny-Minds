"""Stub IntentMind producing deterministic intent labels."""
from __future__ import annotations

import hashlib
from typing import Dict

import numpy as np

from tm_core.base_mind import BaseMind
from tm_core.message_types import MindInput, MindOutput


INTENTS = ["ask", "note", "remind", "search"]


class IntentMind(BaseMind):
    def __init__(self, embed_dim: int = 8) -> None:
        super().__init__(name="intent", version="0.1.0", embed_dim=embed_dim)

    def load(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def save(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def think(self, inp: MindInput) -> MindOutput:
        text = inp.get("text", "") or ""
        digest = hashlib.md5(text.encode("utf-8")).digest()
        intent_idx = digest[0] % len(INTENTS)
        confidence = (digest[1] / 255.0) * 0.5 + 0.5
        rng = np.random.default_rng(int.from_bytes(digest[:4], "little"))
        embedding = rng.normal(size=self.embed_dim).astype(np.float32)
        return MindOutput(
            embedding=embedding,
            confidence=float(confidence),
            labels={"intent": INTENTS[intent_idx]},
            suggestions={},
            aux={"digest": digest.hex()},
        )

    def train_step(self, batch: Dict) -> Dict:
        return {"loss": 0.0}

    def visualize(self, logdir: str) -> None:  # pragma: no cover
        return None

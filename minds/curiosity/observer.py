"""Stub CuriosityMind computing novelty from embeddings."""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from tm_core.base_mind import BaseMind
from tm_core.message_types import MindInput, MindOutput


class CuriosityMind(BaseMind):
    def __init__(self, embed_dim: int = 4) -> None:
        super().__init__(name="curiosity", version="0.1.0", embed_dim=embed_dim)

    def load(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def save(self, ckpt_path: str) -> None:  # pragma: no cover
        return None

    def think(self, inp: MindInput) -> MindOutput:
        context_vec = inp.get("context_vec")
        memory_hits: List[Dict] = inp.get("memory_hits", [])  # type: ignore[assignment]
        novelty = 1.0
        if isinstance(context_vec, np.ndarray) and memory_hits:
            top_score = max(hit.get("score", 0.0) for hit in memory_hits)
            novelty = float(max(0.0, 1.0 - top_score))
        confidence = novelty
        embedding = np.full((self.embed_dim,), novelty, dtype=np.float32)
        return MindOutput(
            embedding=embedding,
            confidence=confidence,
            labels={"novelty": novelty},
            suggestions={},
            aux={"hit_count": len(memory_hits)},
        )

    def train_step(self, batch: Dict) -> Dict:
        return {"loss": 0.0}

    def visualize(self, logdir: str) -> None:  # pragma: no cover
        return None

"""Simple in-memory store backing the orchestrator prototype."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class MemoryEntry:
    text: str
    vec: np.ndarray
    meta: Dict[str, Any]
    entry_id: int


class MemoryStore:
    """Minimal memory store for the development loop."""

    def __init__(self) -> None:
        self._entries: List[MemoryEntry] = []
        self._next_id = 0

    def retrieve(self, query_vec: Optional[np.ndarray], top_k: int = 5) -> List[Dict[str, Any]]:
        if query_vec is None or len(self._entries) == 0:
            return []
        sims: List[Dict[str, Any]] = []
        for entry in self._entries:
            denom = (np.linalg.norm(query_vec) * np.linalg.norm(entry.vec) + 1e-8)
            score = float(np.dot(query_vec, entry.vec) / denom)
            sims.append({"entry_id": entry.entry_id, "score": score, "meta": entry.meta, "text": entry.text})
        sims.sort(key=lambda x: x["score"], reverse=True)
        return sims[:top_k]

    def maybe_write(self, text: str, vec: np.ndarray, meta: Dict[str, Any]) -> int:
        entry = MemoryEntry(text=text, vec=vec, meta=meta, entry_id=self._next_id)
        self._entries.append(entry)
        self._next_id += 1
        return entry.entry_id

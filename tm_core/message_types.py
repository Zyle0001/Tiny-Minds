"""Typed message schemas exchanged between Minds."""
from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict

import numpy as np


class MindInput(TypedDict, total=False):
    text: Optional[str]
    tokens: Optional[list[int]]
    context_vec: Optional[np.ndarray]
    memory_hits: Optional[Dict[str, Any]]
    mind_signals: Optional[Dict[str, Any]]
    meta: Dict[str, Any]


class MindOutput(TypedDict):
    embedding: np.ndarray
    confidence: float
    labels: Dict[str, Any]
    suggestions: Dict[str, Any]
    aux: Dict[str, Any]

from __future__ import annotations

from pathlib import Path

import numpy as np

from tiny_minds.integrations.workspace_memory.analysis import (
    Chunk, EmbeddingCache, add_embedding_signals, lexical_signals, similarity_findings,
)


def chunk(document: str, text: str, record_class: str = "governed") -> Chunk:
    return Chunk(document, record_class, "Heading", 0, text, __import__("hashlib").sha256(text.encode()).hexdigest())


def thresholds() -> dict[str, float]:
    return {
        "governed_embedding": 0.82, "governed_bm25": 0.75,
        "generative_embedding": 0.90, "generative_bm25": 0.85,
        "promotion_embedding": 0.88, "support_embedding": 0.84, "support_bm25": 0.80,
    }


def test_normalized_bm25_is_symmetric_and_deterministic() -> None:
    chunks = [
        chunk("A.md", "alpha beta gamma delta epsilon " * 8),
        chunk("B.md", "alpha beta gamma delta epsilon " * 8),
        chunk("C.md", "walrus copper orbit lantern velvet " * 8),
    ]
    first = lexical_signals(chunks, set())
    second = lexical_signals(chunks, set())
    assert first[("A.md", "B.md")].lexical_score == second[("A.md", "B.md")].lexical_score
    assert first[("A.md", "B.md")].lexical_score > first[("A.md", "C.md")].lexical_score
    assert first[("A.md", "B.md")].lexical_score == 1.0


def test_embedding_cache_keys_include_model_and_content(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "vectors.sqlite3")
    item = chunk("A.md", "stable text")
    key = cache.key(item, "model-a:revision-1:adapter-a")
    cache.put(key, np.array([0.25, 0.75], dtype=np.float32))
    assert np.allclose(cache.get(key), [0.25, 0.75])
    assert cache.get(cache.key(item, "model-a:revision-2:adapter-a")) is None
    assert cache.get(cache.key(chunk("A.md", "changed text"), "model-a:revision-1:adapter-a")) is None
    cache.close()


def test_cosine_routing_keeps_named_signals_and_bounded_excerpts() -> None:
    chunks = [chunk("A.md", "alpha " * 60), chunk("B.md", "beta " * 60)]
    signals = lexical_signals(chunks, set())
    add_embedding_signals(signals, chunks, np.asarray([[1.0, 0.0], [0.83, 0.557763]], dtype=np.float32))
    findings = similarity_findings(signals, thresholds(), {})
    assert len(findings) == 1
    evidence = findings[0].evidence
    assert evidence["embedding_similarity"] >= 0.82
    assert "lexical_score" in evidence
    assert len(evidence["excerpt_a"]) <= 240
    assert len(evidence["excerpt_b"]) <= 240

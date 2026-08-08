from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
import sqlite3
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from . import level1


@dataclass
class Chunk:
    document: str
    record_class: str
    heading: str
    ordinal: int
    text: str
    content_hash: str

    @property
    def chunk_id(self) -> str:
        identity = f"{self.document}#{self.heading}:{self.ordinal}:{self.content_hash}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]

    @property
    def tokens(self) -> list[str]:
        return re.findall(r"[\w'-]+", self.text.lower(), flags=re.UNICODE)

    def excerpt(self, limit: int = 240) -> str:
        compact = re.sub(r"\s+", " ", self.text).strip()
        return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


@dataclass
class PairSignal:
    document_a: str
    document_b: str
    chunk_a: Chunk
    chunk_b: Chunk
    lexical_score: float = 0.0
    embedding_similarity: float | None = None
    cochange_ratio: float | None = None
    shared_commits: int = 0
    existing_relationship: bool = False


def eligible_document(document: level1.Document) -> str | None:
    if document.path.name.upper().endswith("_TEMPLATE.MD") or document.relative in level1.CANONICAL_INDEXES:
        return None
    if document.record_type in level1.GOVERNED_TYPES:
        return "governed"
    if document.record_type == "generative":
        return "generative"
    parts = Path(document.relative).parts
    if len(parts) >= 3 and parts[0] == "Skills" and parts[-1] == "SKILL.md":
        return "skill"
    return None


def chunk_documents(
    documents: list[level1.Document], max_tokens: int = 180, overlap: int = 30, min_tokens: int = 30
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        record_class = eligible_document(document)
        if record_class is None:
            continue
        _, _, body_start = level1.parse_frontmatter(document.text)
        body = "\n".join(document.text.splitlines()[body_start:])
        body = re.sub(r"```.*?```|~~~.*?~~~", "", body, flags=re.DOTALL)
        sections: list[tuple[str, list[str]]] = []
        heading = Path(document.relative).stem
        lines: list[str] = []
        for line in body.splitlines():
            match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
            if match:
                if any(value.strip() for value in lines):
                    sections.append((heading, lines))
                heading = re.sub(r"[*`~]", "", match.group(1)).strip()
                lines = []
            else:
                lines.append(line)
        if any(value.strip() for value in lines):
            sections.append((heading, lines))

        for section_heading, section_lines in sections:
            text = "\n".join(section_lines).strip()
            words = text.split()
            if len(words) < min_tokens:
                continue
            starts = [0] if len(words) <= max_tokens else list(range(0, len(words), max_tokens - overlap))
            for ordinal, start in enumerate(starts):
                piece = " ".join(words[start:start + max_tokens])
                if not piece:
                    continue
                digest = hashlib.sha256(piece.encode("utf-8")).hexdigest()
                chunks.append(Chunk(document.relative, record_class, section_heading, ordinal, piece, digest))
                if start + max_tokens >= len(words):
                    break
    return chunks


def _git_date(path: Path, workspace: Path) -> date | None:
    repo = level1.repository_root(path, workspace)
    if repo:
        try:
            relative = path.resolve().relative_to(repo.resolve()).as_posix()
            dirty = subprocess.run(
                ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "status", "--porcelain", "--", relative],
                capture_output=True, text=True, check=False, timeout=15,
            )
            if dirty.returncode == 0 and dirty.stdout.strip():
                return datetime.fromtimestamp(path.stat().st_mtime).date()
            result = subprocess.run(
                ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "log", "-1", "--format=%cs", "--", relative],
                capture_output=True, text=True, check=False, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return date.fromisoformat(result.stdout.strip().splitlines()[0])
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return None


def freshness_findings(documents: list[level1.Document], workspace: Path) -> list[level1.Finding]:
    findings: list[level1.Finding] = []
    for document in documents:
        if not document.governed:
            continue
        updated = document.metadata.get("updated")
        if not level1.valid_date(updated):
            continue
        verified = date.fromisoformat(updated)
        for source in document.metadata.get("sources", []):
            if not level1.looks_like_local_source(source):
                continue
            resolved = level1.resolve_target(str(source), document, workspace)
            if resolved in {None, Path("__MISSING__")} or not resolved.exists():
                continue
            source_date = _git_date(resolved, workspace)
            if source_date and source_date > verified:
                findings.append(level1.Finding(
                    "source-newer-than-verification", "warning", False,
                    f"Declared source changed after the record was verified: {source}",
                    [document.relative, level1.canonical(resolved, workspace)],
                    {"source": str(source), "verified": verified.isoformat(), "source_date": source_date.isoformat()},
                ))
    return findings


def relationship_pairs(documents: list[level1.Document], workspace: Path) -> set[tuple[str, str]]:
    by_path = {document.path.resolve(): document.relative for document in documents}
    relationships: set[tuple[str, str]] = set()
    for document in documents:
        targets: list[tuple[str, bool]] = []
        targets.extend((target, kind == "wiki") for kind, target in level1.extract_links(document))
        for field in ("related", "supersedes"):
            values = document.metadata.get(field, [])
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str):
                        targets.append(level1.metadata_target(value))
        sources = document.metadata.get("sources", [])
        if isinstance(sources, list):
            for value in sources:
                if isinstance(value, str) and level1.looks_like_local_source(value):
                    targets.append((value, False))
        for target, wiki in targets:
            resolved = level1.resolve_target(target, document, workspace, wiki)
            if resolved in by_path:
                relationships.add(tuple(sorted((document.relative, by_path[resolved]))))
    return relationships


def cochange_pairs(documents: list[level1.Document], workspace: Path) -> dict[tuple[str, str], tuple[float, int]]:
    eligible = [document for document in documents if eligible_document(document) in {"governed", "skill"}]
    by_repo: dict[Path, list[level1.Document]] = defaultdict(list)
    for document in eligible:
        repo = level1.repository_root(document.path, workspace)
        if repo:
            by_repo[repo].append(document)
    output: dict[tuple[str, str], tuple[float, int]] = {}
    for repo, repo_documents in by_repo.items():
        commit_sets: dict[str, set[str]] = {}
        for document in repo_documents:
            relative = document.path.resolve().relative_to(repo.resolve()).as_posix()
            try:
                result = subprocess.run(
                    ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "log", "--format=%H", "--", relative],
                    capture_output=True, text=True, check=False, timeout=30,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if result.returncode == 0:
                commit_sets[document.relative] = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        for a, b in itertools.combinations(sorted(commit_sets), 2):
            shared = len(commit_sets[a] & commit_sets[b])
            union = len(commit_sets[a] | commit_sets[b])
            if shared >= 3 and union:
                ratio = shared / union
                if ratio >= 0.5:
                    output[(a, b)] = (ratio, shared)
    return output


def cochange_findings(
    pairs: dict[tuple[str, str], tuple[float, int]], relationships: set[tuple[str, str]]
) -> list[level1.Finding]:
    findings: list[level1.Finding] = []
    for pair, (ratio, shared) in sorted(pairs.items()):
        if pair in relationships:
            continue
        findings.append(level1.Finding(
            "cochange-undocumented", "warning", False,
            f"Records changed together in {shared} commits (Jaccard {ratio:.3f}) without a documented relationship",
            list(pair), {"section_pair": list(pair), "cochange_ratio": round(ratio, 6), "shared_commits": shared},
        ))
    return findings


def lexical_signals(chunks: list[Chunk], relationships: set[tuple[str, str]]) -> dict[tuple[str, str], PairSignal]:
    tokenized = [chunk.tokens for chunk in chunks]
    document_frequency: Counter[str] = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))
    count = len(chunks)
    average_length = sum(map(len, tokenized)) / max(1, count)
    idf = {term: math.log(1.0 + (count - frequency + 0.5) / (frequency + 0.5)) for term, frequency in document_frequency.items()}

    def directed(query: list[str], target: list[str]) -> float:
        frequencies = Counter(target)
        length = len(target)
        score = 0.0
        for term in set(query):
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            numerator = frequency * 2.5
            denominator = frequency + 1.5 * (1.0 - 0.75 + 0.75 * length / max(1.0, average_length))
            score += idf.get(term, 0.0) * numerator / denominator
        return score

    self_scores = [directed(tokens, tokens) for tokens in tokenized]
    best: dict[tuple[str, str], PairSignal] = {}
    for left in range(count):
        for right in range(left + 1, count):
            if chunks[left].document == chunks[right].document:
                continue
            forward = directed(tokenized[left], tokenized[right]) / max(self_scores[left], 1e-12)
            reverse = directed(tokenized[right], tokenized[left]) / max(self_scores[right], 1e-12)
            score = max(0.0, min(1.0, (forward + reverse) / 2.0))
            pair = tuple(sorted((chunks[left].document, chunks[right].document)))
            current = best.get(pair)
            if current is None or score > current.lexical_score:
                a, b = (chunks[left], chunks[right]) if chunks[left].document == pair[0] else (chunks[right], chunks[left])
                best[pair] = PairSignal(pair[0], pair[1], a, b, lexical_score=score, existing_relationship=pair in relationships)
    return best


class EmbeddingCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS embeddings (cache_key TEXT PRIMARY KEY, dimensions INTEGER NOT NULL, vector BLOB NOT NULL)"
        )

    @staticmethod
    def key(chunk: Chunk, model_identity: str) -> str:
        return hashlib.sha256(f"{model_identity}:{chunk.content_hash}".encode("utf-8")).hexdigest()

    def get(self, key: str) -> np.ndarray | None:
        row = self.connection.execute("SELECT dimensions, vector FROM embeddings WHERE cache_key=?", (key,)).fetchone()
        if row is None:
            return None
        vector = np.frombuffer(row[1], dtype=np.float32)
        return vector if vector.shape == (int(row[0]),) else None

    def put(self, key: str, vector: np.ndarray) -> None:
        cooked = np.asarray(vector, dtype=np.float32)
        self.connection.execute(
            "INSERT OR REPLACE INTO embeddings(cache_key, dimensions, vector) VALUES(?,?,?)",
            (key, int(cooked.shape[0]), cooked.tobytes()),
        )

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()


def add_embedding_signals(signals: dict[tuple[str, str], PairSignal], chunks: list[Chunk], vectors: np.ndarray) -> None:
    if len(chunks) == 0:
        return
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / np.maximum(norms, np.finfo(np.float32).eps)
    similarities = matrix @ matrix.T
    for left in range(len(chunks)):
        for right in range(left + 1, len(chunks)):
            if chunks[left].document == chunks[right].document:
                continue
            pair = tuple(sorted((chunks[left].document, chunks[right].document)))
            score = float(similarities[left, right])
            current = signals.get(pair)
            if current is None:
                a, b = (chunks[left], chunks[right]) if chunks[left].document == pair[0] else (chunks[right], chunks[left])
                current = PairSignal(pair[0], pair[1], a, b)
                signals[pair] = current
            if current.embedding_similarity is None or score > current.embedding_similarity:
                current.embedding_similarity = score
                current.chunk_a, current.chunk_b = (
                    (chunks[left], chunks[right]) if chunks[left].document == pair[0] else (chunks[right], chunks[left])
                )


def similarity_findings(
    signals: dict[tuple[str, str], PairSignal], thresholds: dict[str, float], cochange: dict[tuple[str, str], tuple[float, int]]
) -> list[level1.Finding]:
    findings: list[level1.Finding] = []
    for pair, signal in sorted(signals.items()):
        classes = {signal.chunk_a.record_class, signal.chunk_b.record_class}
        lexical = signal.lexical_score
        semantic = signal.embedding_similarity
        label: str | None = None
        qualifies = False
        if "generative" not in classes:
            qualifies = lexical >= thresholds["governed_bm25"] or (semantic is not None and semantic >= thresholds["governed_embedding"])
            label = "possible-near-duplicate" if lexical >= thresholds["governed_bm25"] else "possible-semantic-overlap"
        elif classes == {"generative"}:
            qualifies = (
                lexical >= thresholds["generative_bm25"]
                or (semantic is not None and semantic >= thresholds["generative_embedding"])
                or (semantic is not None and semantic >= thresholds["support_embedding"] and lexical >= thresholds["support_bm25"])
            )
            label = "possible-generative-overlap"
        else:
            qualifies = semantic is not None and (
                semantic >= thresholds["promotion_embedding"]
                or (semantic >= thresholds["support_embedding"] and lexical >= thresholds["support_bm25"])
            )
            label = "possible-promotion-or-overlap"
        if not qualifies:
            continue
        if signal.existing_relationship:
            label = "documented-overlap"
        ratio, shared = cochange.get(pair, (None, 0))
        evidence = {
            "section_pair": [signal.chunk_a.chunk_id, signal.chunk_b.chunk_id],
            "section_a": signal.chunk_a.heading,
            "section_b": signal.chunk_b.heading,
            "chunk_a": signal.chunk_a.chunk_id,
            "chunk_b": signal.chunk_b.chunk_id,
            "content_sha256_a": signal.chunk_a.content_hash,
            "content_sha256_b": signal.chunk_b.content_hash,
            "lexical_score": round(lexical, 6),
            "embedding_similarity": round(semantic, 6) if semantic is not None else None,
            "cochange_ratio": round(ratio, 6) if ratio is not None else None,
            "shared_commits": shared,
            "existing_relationship": signal.existing_relationship,
            "classification": label,
            "excerpt_a": signal.chunk_a.excerpt(),
            "excerpt_b": signal.chunk_b.excerpt(),
        }
        findings.append(level1.Finding(
            "similarity-candidate", "warning", False,
            f"{label}: lexical={lexical:.3f}, semantic={semantic:.3f}" if semantic is not None else f"{label}: lexical={lexical:.3f}",
            list(pair), evidence,
        ))
    return findings

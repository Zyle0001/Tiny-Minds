from __future__ import annotations

import fnmatch
import hashlib
import math
import re
import json
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path
from typing import Iterable
from typing import Any

from .contracts import ArtifactRef, ChunkRef, WorkspaceScope


TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'’-]*")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tokens(text: str) -> list[str]:
    return [item.casefold() for item in TOKEN_RE.findall(text)]


def canonical_path(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        return resolved.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Path '{path}' is outside scope root '{root}'") from exc


def inventory(scope: WorkspaceScope, base: Path) -> list[Path]:
    root = (base / scope.root).resolve() if not Path(scope.root).is_absolute() else Path(scope.root).resolve()
    if not root.is_dir():
        raise ValueError(f"Scope root '{root}' is not a directory")
    found: dict[str, Path] = {}
    for pattern in scope.include:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            rel = canonical_path(root, path)
            if any(fnmatch.fnmatch(rel, excluded) or fnmatch.fnmatch(path.name, excluded) for excluded in scope.exclude):
                continue
            found[rel] = path
    return [found[key] for key in sorted(found)]


def artifact_for(path: Path, root: Path, media_type: str | None = None) -> ArtifactRef:
    raw = path.read_bytes()
    guessed = media_type or ("text/markdown" if path.suffix.casefold() in {".md", ".markdown"} else "text/plain")
    return ArtifactRef(
        uri=canonical_path(root, path), media_type=guessed, content_sha256=sha256_bytes(raw), size_bytes=len(raw)
    )


def chunk_markdown(path: Path, root: Path, *, max_tokens: int = 180, overlap: int = 30) -> list[tuple[ChunkRef, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    artifact = artifact_for(path, root)
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    body: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        match = None if in_fence else HEADING_RE.match(line)
        if match:
            if body:
                sections.append((heading, "\n".join(body).strip()))
            heading, body = match.group(2).strip(), []
        elif not in_fence:
            body.append(line)
    if body or not sections:
        sections.append((heading, "\n".join(body).strip()))
    output: list[tuple[ChunkRef, str]] = []
    ordinal = 0
    for section_heading, section_text in sections:
        words = section_text.split()
        if not words:
            continue
        step = max(1, max_tokens - overlap)
        starts = range(0, len(words), step) if len(words) > max_tokens else (0,)
        for start in starts:
            content = " ".join(words[start : start + max_tokens])
            digest = sha256_bytes(content.encode("utf-8"))
            chunk_id = f"{artifact.uri}#{section_heading or '_root'}:{ordinal}:{digest[:12]}"
            output.append((ChunkRef(
                artifact=artifact, chunk_id=chunk_id, heading=section_heading, ordinal=ordinal,
                content_sha256=digest, excerpt=content[:240],
            ), content))
            ordinal += 1
            if start + max_tokens >= len(words):
                break
    return output


def normalized_bm25(query: str, documents: list[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
    if not documents:
        return []
    query_terms = set(tokens(query))
    tokenized = [tokens(item) for item in documents]
    average = sum(map(len, tokenized)) / max(1, len(tokenized))
    document_frequency = Counter(term for term in query_terms for doc in tokenized if term in set(doc))
    raw: list[float] = []
    for doc in tokenized:
        counts = Counter(doc)
        score = 0.0
        for term in query_terms:
            tf = counts[term]
            if not tf:
                continue
            idf = max(0.0, math.log(1.0 + (len(documents) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5)))
            denominator = tf + k1 * (1.0 - b + b * len(doc) / max(1.0, average))
            score += idf * tf * (k1 + 1.0) / denominator
        raw.append(score)
    maximum = max(raw, default=0.0)
    return [item / maximum if maximum else 0.0 for item in raw]


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0


def git(root: Path, *args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return result.returncode, result.stdout.strip()


def within_patterns(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def provider_identity(provider: object, model_id: str | None = None) -> dict[str, Any]:
    identity = getattr(provider, "cache_identity", None)
    if callable(identity):
        value = identity(model_id) if model_id is not None else identity()
        if isinstance(value, dict):
            return value
    return {
        "provider_id": str(getattr(provider, "provider_id", provider.__class__.__name__)),
        "implementation": f"{provider.__class__.__module__}.{provider.__class__.__qualname__}",
        "model_id": model_id,
    }


class JsonCache:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    @staticmethod
    def key(operation: str, identity: dict[str, Any], payload: Any) -> str:
        encoded = json.dumps({"operation": operation, "identity": identity, "payload": payload}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        if self.path is None or not self.path.is_file():
            return None
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            row = connection.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, key: str, value: Any) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT OR REPLACE INTO cache(key, value) VALUES (?, ?)", (key, json.dumps(value, separators=(",", ":"))))

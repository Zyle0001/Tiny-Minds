from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..contracts import EvidenceReference, PrimitiveMetrics, PrimitiveResult, Provenance, WorkspaceScope
from ..engine import ExecutionContext
from ..generic import JsonCache, chunk_markdown, cosine, git, inventory, normalized_bm25, provider_identity, sha256_bytes, tokens, within_patterns
from ..providers import (
    ClassificationProvider, ClassificationRequest, EmbeddingProvider, EmbeddingRequest,
    NliPair, NliProvider, NliRequest, NliScores, ProviderUnavailable, RerankingProvider, RerankRequest,
)
from ..registry import CapabilityRegistry


VERSION = "0.2.0"


def _result(capability: str, data: dict[str, Any], *, scores: dict[str, float] | None = None,
            evidence: list[EvidenceReference] | None = None, candidates: int = 0,
            diagnostics: list[str] | None = None, cache_hits: int = 0, cache_misses: int = 0,
            verification: list[dict[str, Any]] | None = None) -> PrimitiveResult:
    return PrimitiveResult(
        capability=capability, version=VERSION, status="degraded" if diagnostics else "success", data=data,
        scores=scores or {}, evidence=evidence or [],
        provenance=Provenance(implementation=__name__, version=VERSION, verification=verification or []),
        metrics=PrimitiveMetrics(candidate_count=candidates, cache_hits=cache_hits, cache_misses=cache_misses), diagnostics=diagnostics or [],
    )


def _scope(context: ExecutionContext) -> WorkspaceScope:
    return WorkspaceScope.model_validate(context.request.inputs.get("scope", {}))


def _text_documents(context: ExecutionContext) -> list[tuple[str, str, str | None]]:
    supplied = context.request.inputs.get("documents")
    if supplied is not None:
        if not isinstance(supplied, list):
            raise ValueError("documents must be a list")
        output = []
        for index, item in enumerate(supplied):
            if isinstance(item, str):
                output.append((f"input:{index}", item, None))
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                output.append((str(item.get("path", f"input:{index}")), item["text"], item.get("heading")))
            else:
                raise ValueError("each document must be text or a mapping containing text")
        return output
    scope = _scope(context)
    root = (context.workspace / scope.root).resolve() if not Path(scope.root).is_absolute() else Path(scope.root).resolve()
    output: list[tuple[str, str, str | None]] = []
    for path in inventory(scope, context.workspace):
        if path.suffix.casefold() in {".md", ".markdown"}:
            for chunk, content in chunk_markdown(path, root):
                output.append((chunk.artifact.uri, content, chunk.heading))
        elif path.suffix.casefold() in {".txt", ".log", ".json", ".yaml", ".yml"}:
            output.append((path.relative_to(root).as_posix(), path.read_text(encoding="utf-8", errors="replace"), None))
    return output


def _provider(context: ExecutionContext, provider_id: str, protocol: type) -> object | None:
    provider = context.providers.get(provider_id)
    return provider if provider is not None and isinstance(provider, protocol) else None


def _cache(context: ExecutionContext) -> JsonCache:
    if context.request.inputs.get("no_write"):
        return JsonCache(None)
    return JsonCache(Path(context.request.inputs.get("cache_path", context.workspace / "tmp" / "tiny-minds" / "generic-cache.sqlite")))


class ValidateScopedDelta:
    capability = "workspace.validate-scoped-delta"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        before = context.request.inputs.get("before", {})
        after = context.request.inputs.get("after", {})
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise ValueError("before and after must be path-to-hash mappings")
        allow = [str(item) for item in context.request.inputs.get("allowed", config.get("allowed", []))]
        generated = [str(item) for item in context.request.inputs.get("generated", config.get("generated", []))]
        changes = []
        for path in sorted(set(before) | set(after)):
            if path not in before:
                status = "added"
            elif path not in after:
                status = "deleted"
            elif before[path] != after[path]:
                status = "modified"
            else:
                continue
            changes.append({"path": path, "status": status, "allowed": within_patterns(path, allow),
                            "generated": within_patterns(path, generated)})
        violations = [item for item in changes if not item["allowed"]]
        return _result(self.capability, {"valid": not violations, "changes": changes, "violations": violations},
                       scores={"violation_count": float(len(violations))}, candidates=len(changes))


def _git_changes(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    code, status = git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if code:
        return [], ["Git history is unavailable for this scope"]
    entries: list[dict[str, Any]] = []
    mapping = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed", "?": "untracked"}
    for line in status.splitlines():
        if len(line) < 4:
            continue
        marker = line[:2]
        raw_path = line[3:]
        previous = None
        if " -> " in raw_path:
            previous, raw_path = raw_path.split(" -> ", 1)
        symbol = next((char for char in marker if char != " "), "?")
        entries.append({"path": raw_path, "status": mapping.get(symbol, "modified"), "previous_path": previous})
    return entries, []


class ChangePacket:
    capability = "workspace.change-packet"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        root = Path(context.request.inputs.get("repository", context.workspace)).resolve()
        limit = int(context.request.constraints.get("max_candidates", config.get("max_files", 200)))
        entries, diagnostics = _git_changes(root)
        code, branch = git(root, "branch", "--show-current")
        code_head, head = git(root, "rev-parse", "HEAD")
        code_num, numstat = git(root, "diff", "--numstat")
        stats: dict[str, tuple[int, int]] = {}
        if code_num == 0:
            for line in numstat.splitlines():
                parts = line.split("\t", 2)
                if len(parts) == 3:
                    stats[parts[2]] = tuple(int(value) if value.isdigit() else 0 for value in parts[:2])
        for entry in entries:
            additions, deletions = stats.get(entry["path"], (0, 0))
            entry.update(additions=additions, deletions=deletions)
        omitted = max(0, len(entries) - limit)
        selected = entries[:limit]
        return _result(self.capability, {
            "repository": str(root), "branch": branch if code == 0 else None,
            "head": head if code_head == 0 else None, "dirty": bool(entries),
            "changes": selected, "omitted_count": omitted,
        }, candidates=len(entries), diagnostics=diagnostics)


class RepoPreflight:
    capability = "repo.preflight"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        root = Path(context.request.inputs.get("repository", context.workspace)).resolve()
        code, top = git(root, "rev-parse", "--show-toplevel")
        blockers: list[str] = []
        warnings: list[str] = []
        if code:
            blockers.append("The requested path is not a Git worktree")
        entries, diagnostics = _git_changes(root)
        code_branch, branch = git(root, "branch", "--show-current")
        if code_branch == 0 and not branch:
            warnings.append("Repository is in detached HEAD state")
        instruction_files = [name for name in ("AGENTS.md", "CONTRIBUTING.md", "README.md") if (root / name).is_file()]
        validations = []
        if (root / "pyproject.toml").is_file():
            validations.append("python -m pytest")
        if (root / "package.json").is_file():
            validations.append("npm test")
        if (root / "Cargo.toml").is_file():
            validations.append("cargo test")
        nested = []
        for child in root.iterdir() if root.is_dir() else []:
            if child.is_dir() and (child / ".git").exists():
                nested.append(child.name)
        return _result(self.capability, {
            "ready": not blockers, "repository": top if code == 0 else str(root), "branch": branch or None,
            "dirty": bool(entries), "changed_paths": [item["path"] for item in entries],
            "instruction_files": instruction_files, "nested_repositories": nested,
            "recommended_validations": validations, "blockers": blockers, "warnings": warnings,
        }, diagnostics=diagnostics, candidates=len(entries))


def _rank_context(context: ExecutionContext, query: str, docs: list[tuple[str, str, str | None]], limit: int) -> tuple[list[dict], list[str], int, int, list[dict[str, Any]]]:
    texts = [item[1] for item in docs]
    lexical = normalized_bm25(query, texts)
    semantic = [0.0] * len(docs)
    reranker = [0.0] * len(docs)
    diagnostics: list[str] = []
    cache = _cache(context)
    cache_hits = cache_misses = 0
    verification: list[dict[str, Any]] = []
    embedder = _provider(context, "embeddings", EmbeddingProvider)
    if embedder:
        try:
            verification.append(provider_identity(embedder))
            embedding_payload = [sha256_bytes(item.encode("utf-8")) for item in [query, *texts]]
            embedding_key = cache.key("embed", provider_identity(embedder), embedding_payload)
            vectors = cache.get(embedding_key)
            if vectors is None:
                cache_misses += 1
                response = embedder.embed(EmbeddingRequest(texts=[query, *texts]))
                vectors = response.vectors
                cache.set(embedding_key, vectors)
            else:
                cache_hits += 1
            if len(vectors) == len(texts) + 1:
                semantic = [max(0.0, cosine(vectors[0], vector)) for vector in vectors[1:]]
        except ProviderUnavailable as exc:
            diagnostics.append(str(exc))
    else:
        diagnostics.append("Embedding provider unavailable; lexical retrieval continued")
    first_pass = sorted(range(len(docs)), key=lambda i: (0.55 * lexical[i] + 0.45 * semantic[i]), reverse=True)[: max(limit * 4, limit)]
    pair_provider = _provider(context, "reranker", RerankingProvider)
    if pair_provider and first_pass:
        try:
            verification.append(provider_identity(pair_provider))
            rerank_payload = {"query": sha256_bytes(query.encode()), "documents": [sha256_bytes(texts[i].encode()) for i in first_pass]}
            rerank_key = cache.key("rerank", provider_identity(pair_provider), rerank_payload)
            pair_scores = cache.get(rerank_key)
            if pair_scores is None:
                cache_misses += 1
                pair_scores = pair_provider.rerank(RerankRequest(query=query, documents=[texts[i] for i in first_pass])).scores
                cache.set(rerank_key, pair_scores)
            else:
                cache_hits += 1
            for index, score in zip(first_pass, pair_scores):
                reranker[index] = float(score)
        except ProviderUnavailable as exc:
            diagnostics.append(str(exc))
    ranked = sorted(first_pass, key=lambda i: (0.4 * lexical[i] + 0.3 * semantic[i] + 0.3 * reranker[i]), reverse=True)[:limit]
    return [{"path": docs[i][0], "heading": docs[i][2], "excerpt": docs[i][1][:240],
             "content_sha256": sha256_bytes(docs[i][1].encode("utf-8")),
             "scores": {"lexical": lexical[i], "embedding": semantic[i], "reranker": reranker[i]}}
            for i in ranked], diagnostics, cache_hits, cache_misses, verification


class RetrieveContext:
    capability = "workspace.retrieve-context"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        query = str(context.request.inputs.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        limit = min(int(context.request.inputs.get("limit", config.get("limit", 8))), context.manifest.budgets.max_candidates)
        docs = _text_documents(context)
        ranked, diagnostics, cache_hits, cache_misses, verification = _rank_context(context, query, docs, limit)
        evidence = [EvidenceReference(path=item["path"], heading=item["heading"], content_sha256=item["content_sha256"], excerpt=item["excerpt"]) for item in ranked]
        return _result(self.capability, {"query_sha256": sha256_bytes(query.encode()), "results": ranked,
                                        "degraded": bool(diagnostics)}, evidence=evidence,
                       candidates=len(docs), diagnostics=diagnostics, cache_hits=cache_hits, cache_misses=cache_misses,
                       verification=verification)


class SemanticDuplicate:
    capability = "workspace.semantic-duplicate"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        target = str(context.request.inputs.get("target", ""))
        if not target:
            raise ValueError("target text is required")
        docs = _text_documents(context)
        limit = int(config.get("limit", 10))
        ranked, diagnostics, cache_hits, cache_misses, verification = _rank_context(context, target, docs, limit)
        target_hash = sha256_bytes(target.encode("utf-8"))
        for candidate in ranked:
            candidate["exact"] = candidate["content_sha256"] == target_hash
            candidate["review"] = candidate["exact"] or max(candidate["scores"].values()) >= float(config.get("review_threshold", 0.80))
        exact = [item for item in ranked if item["exact"]]
        review = [item for item in ranked if item["review"] and not item["exact"]]
        return _result(self.capability, {"exact_duplicate": bool(exact), "exact": exact, "review_candidates": review},
                       scores={"exact_count": float(len(exact)), "review_count": float(len(review))},
                       candidates=len(docs), diagnostics=diagnostics, cache_hits=cache_hits, cache_misses=cache_misses,
                       verification=verification)


class ClassifyArtifact:
    capability = "workspace.classify-artifact"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        text = str(context.request.inputs.get("text", ""))
        path = str(context.request.inputs.get("path", ""))
        taxonomy = context.request.inputs.get("taxonomy")
        if not isinstance(taxonomy, dict) or not taxonomy:
            raise ValueError("taxonomy must be a non-empty label mapping")
        scores: dict[str, dict[str, float]] = {}
        descriptions: list[str] = []
        for label, definition in taxonomy.items():
            spec = definition if isinstance(definition, dict) else {"description": str(definition)}
            description = str(spec.get("description", label))
            descriptions.append(description)
            lexical = len(set(tokens(text)) & set(tokens(description))) / max(1, len(set(tokens(description))))
            extension = 1.0 if any(path.casefold().endswith(str(ext).casefold()) for ext in spec.get("extensions", [])) else 0.0
            scores[str(label)] = {"rule": extension, "lexical": lexical, "embedding": 0.0, "nli": 0.0}
        classifier = _provider(context, "classification", ClassificationProvider)
        embedder = _provider(context, "embeddings", EmbeddingProvider)
        diagnostics: list[str] = []
        cache, cache_hits, cache_misses = _cache(context), 0, 0
        verification: list[dict[str, Any]] = []
        if embedder:
            try:
                verification.append(provider_identity(embedder))
                payload_hashes = [sha256_bytes(item.encode()) for item in [text, *descriptions]]
                key = cache.key("classify-embed", provider_identity(embedder), payload_hashes)
                vectors = cache.get(key)
                if vectors is None:
                    cache_misses += 1
                    vectors = embedder.embed(EmbeddingRequest(texts=[text, *descriptions])).vectors
                    cache.set(key, vectors)
                else:
                    cache_hits += 1
                if len(vectors) == len(descriptions) + 1:
                    for label, vector in zip(scores, vectors[1:]):
                        scores[label]["embedding"] = max(0.0, cosine(vectors[0], vector))
            except ProviderUnavailable as exc:
                diagnostics.append(str(exc))
        else:
            diagnostics.append("Embedding provider unavailable; prototype similarity was skipped")
        if classifier:
            try:
                verification.append(provider_identity(classifier))
                key = cache.key("classify-nli", provider_identity(classifier), {"text": sha256_bytes(text.encode()), "labels": list(scores)})
                model_rows = cache.get(key)
                if model_rows is None:
                    cache_misses += 1
                    model_rows = classifier.classify(ClassificationRequest(texts=[text], labels=list(scores))).scores
                    cache.set(key, model_rows)
                else:
                    cache_hits += 1
                if model_rows:
                    for label, value in model_rows[0].items():
                        if label in scores:
                            scores[label]["nli"] = float(value)
            except ProviderUnavailable as exc:
                diagnostics.append(str(exc))
        else:
            diagnostics.append("Classification provider unavailable; rules and lexical evidence continued")
        totals = {label: 0.35 * value["rule"] + 0.15 * value["lexical"] + 0.20 * value["embedding"] + 0.30 * value["nli"] for label, value in scores.items()}
        ranked = sorted(totals, key=totals.get, reverse=True)
        margin = totals[ranked[0]] - (totals[ranked[1]] if len(ranked) > 1 else 0.0)
        resolved = totals[ranked[0]] >= float(config.get("threshold", 0.65)) and margin >= float(config.get("margin", 0.15))
        return _result(self.capability, {"label": ranked[0] if resolved else None, "resolved": resolved,
                                        "alternatives": [{"label": label, "score": totals[label], "signals": scores[label]} for label in ranked]},
                       scores={"top_score": totals[ranked[0]], "margin": margin}, diagnostics=diagnostics,
                       candidates=len(scores), cache_hits=cache_hits, cache_misses=cache_misses,
                       verification=verification)


class ClaimEvidenceReview:
    capability = "text.claim-evidence-review"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        pairs = context.request.inputs.get("pairs")
        if not isinstance(pairs, list) or not pairs:
            raise ValueError("pairs must contain claim/evidence mappings")
        prepared = []
        for item in pairs:
            if not isinstance(item, dict) or not isinstance(item.get("claim"), str) or not isinstance(item.get("evidence"), str):
                raise ValueError("each pair requires string claim and evidence fields")
            prepared.append((item["claim"], item["evidence"]))
        model_scores = None
        diagnostics: list[str] = []
        cache, cache_hits, cache_misses = _cache(context), 0, 0
        verification: list[dict[str, Any]] = []
        provider = _provider(context, "nli", NliProvider)
        if provider:
            try:
                verification.append(provider_identity(provider))
                pair_hashes = [{"claim": sha256_bytes(claim.encode()), "evidence": sha256_bytes(evidence.encode())} for claim, evidence in prepared]
                key = cache.key("claim-nli", provider_identity(provider), pair_hashes)
                cached_scores = cache.get(key)
                if cached_scores is None:
                    cache_misses += 1
                    model_scores = provider.nli(NliRequest(pairs=[NliPair(premise=evidence, hypothesis=claim) for claim, evidence in prepared])).scores
                    cache.set(key, [item.model_dump() for item in model_scores])
                else:
                    cache_hits += 1
                    model_scores = [NliScores.model_validate(row) for row in cached_scores]
            except ProviderUnavailable as exc:
                diagnostics.append(str(exc))
        else:
            diagnostics.append("NLI provider unavailable; deterministic overlap evidence continued")
        relevance = [0.0] * len(prepared)
        reranker = _provider(context, "reranker", RerankingProvider)
        if reranker:
            verification.append(provider_identity(reranker))
            for index, (claim, evidence) in enumerate(prepared):
                key = cache.key("claim-rerank", provider_identity(reranker), {"claim": sha256_bytes(claim.encode()), "evidence": sha256_bytes(evidence.encode())})
                cached = cache.get(key)
                if cached is None:
                    cache_misses += 1
                    cached = reranker.rerank(RerankRequest(query=claim, documents=[evidence])).scores
                    cache.set(key, cached)
                else:
                    cache_hits += 1
                relevance[index] = float(cached[0]) if cached else 0.0
        else:
            diagnostics.append("Reranker unavailable; evidence relevance used lexical overlap only")
        results = []
        for index, (claim, evidence) in enumerate(prepared):
            overlap = len(set(tokens(claim)) & set(tokens(evidence))) / max(1, len(set(tokens(claim))))
            negation_mismatch = bool(re.search(r"\b(no|not|never|without)\b", claim, re.I)) != bool(re.search(r"\b(no|not|never|without)\b", evidence, re.I))
            nli = model_scores[index].model_dump() if model_scores and index < len(model_scores) else {"contradiction": 0.0, "entailment": 0.0, "neutral": 0.0}
            if nli["entailment"] >= float(config.get("entailment_threshold", 0.70)):
                relation = "supported"
            elif nli["contradiction"] >= float(config.get("contradiction_threshold", 0.70)) or (overlap >= 0.6 and negation_mismatch):
                relation = "contradicted"
            else:
                relation = "insufficient-evidence"
            results.append({"claim_sha256": sha256_bytes(claim.encode()), "evidence_sha256": sha256_bytes(evidence.encode()),
                            "relation": relation, "scores": {**nli, "lexical": overlap, "reranker": relevance[index]}})
        return _result(self.capability, {"relationships": results}, candidates=len(results), diagnostics=diagnostics,
                       cache_hits=cache_hits, cache_misses=cache_misses, verification=verification)


class SessionContextPacket:
    capability = "session.context-packet"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        maximum = int(context.request.constraints.get("max_output_bytes", config.get("max_output_bytes", 16_000)))
        items: list[dict[str, Any]] = []
        unresolved: list[str] = []
        degradation: list[str] = []
        for name, dependency in dependencies.items():
            degradation.extend(dependency.diagnostics)
            if dependency.status != "success":
                unresolved.append(f"Dependency {name} completed as {dependency.status}")
            if dependency.capability == "workspace.retrieve-context":
                items.extend(dependency.data.get("results", []))
            elif dependency.capability in {"workspace.change-packet", "repo.preflight"}:
                items.append({"source": dependency.capability, "data": dependency.data})
        encoded_items, used, omitted = [], 0, 0
        seen: set[str] = set()
        for item in items:
            digest = hashlib.sha256(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            size = len(json.dumps(item, default=str).encode())
            if used + size > maximum:
                omitted += 1
                continue
            encoded_items.append(item)
            used += size
        return _result(self.capability, {"items": encoded_items, "unresolved": unresolved,
                                        "degradation": degradation, "omitted_count": omitted, "output_bytes": used}, candidates=len(items))


class LyricAudit:
    capability = "creative.lyric-audit"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        lyric = str(context.request.inputs.get("lyrics", ""))
        if not lyric.strip():
            raise ValueError("lyrics are required")
        sections: dict[str, list[str]] = defaultdict(list)
        current = "unlabelled"
        for line in lyric.splitlines():
            match = re.match(r"^\s*\[([^]]+)]\s*$", line)
            if match:
                current = match.group(1).strip()
            elif line.strip():
                sections[current].append(line.strip())
        all_lines = [line for lines in sections.values() for line in lines]
        normalized = [" ".join(tokens(line)) for line in all_lines]
        repetitions = {line: count for line, count in Counter(normalized).items() if line and count > 1}
        lengths = [len(tokens(line)) for line in all_lines]
        mean = sum(lengths) / max(1, len(lengths))
        variance = sum((value - mean) ** 2 for value in lengths) / max(1, len(lengths))
        production_terms = set(config.get("production_terms", ["bassline", "reverb", "compressor", "sidechain", "bpm", "synth", "mixdown"]))
        contamination = sorted(set(tokens(lyric)) & production_terms)
        section_vocab = {name: set(tokens(" ".join(lines))) for name, lines in sections.items()}
        redundancies = []
        names = list(section_vocab)
        for i, left in enumerate(names):
            for right in names[i + 1:]:
                union = section_vocab[left] | section_vocab[right]
                similarity = len(section_vocab[left] & section_vocab[right]) / max(1, len(union))
                if similarity >= float(config.get("section_similarity", 0.6)):
                    redundancies.append({"left": left, "right": right, "lexical_similarity": similarity})
        diagnostics: list[str] = []
        verification: list[dict[str, Any]] = []
        cache, cache_hits, cache_misses = _cache(context), 0, 0
        model_section_scores: list[dict[str, Any]] = []
        embedder = _provider(context, "embeddings", EmbeddingProvider)
        if embedder and len(sections) > 1:
            try:
                verification.append(provider_identity(embedder))
                names = list(sections)
                section_texts = [" ".join(sections[name]) for name in names]
                key = cache.key("lyric-sections", provider_identity(embedder), [sha256_bytes(item.encode()) for item in section_texts])
                vectors = cache.get(key)
                if vectors is None:
                    cache_misses += 1
                    vectors = embedder.embed(EmbeddingRequest(texts=section_texts)).vectors
                    cache.set(key, vectors)
                else:
                    cache_hits += 1
                for i, left in enumerate(names):
                    for j, right in enumerate(names[i + 1:], i + 1):
                        model_section_scores.append({"left": left, "right": right, "embedding_similarity": max(0.0, cosine(vectors[i], vectors[j]))})
            except ProviderUnavailable as exc:
                diagnostics.append(str(exc))
        elif len(sections) > 1:
            diagnostics.append("Embedding provider unavailable; thematic drift used lexical evidence only")
        brief_fidelity = None
        brief = context.request.inputs.get("brief")
        nli_provider = _provider(context, "nli", NliProvider)
        if isinstance(brief, str) and brief.strip() and nli_provider:
            try:
                verification.append(provider_identity(nli_provider))
                key = cache.key("lyric-brief", provider_identity(nli_provider), {"lyric": sha256_bytes(lyric.encode()), "brief": sha256_bytes(brief.encode())})
                brief_fidelity = cache.get(key)
                if brief_fidelity is None:
                    cache_misses += 1
                    brief_fidelity = nli_provider.nli(NliRequest(pairs=[NliPair(premise=lyric, hypothesis=brief)])).scores[0].model_dump()
                    cache.set(key, brief_fidelity)
                else:
                    cache_hits += 1
            except ProviderUnavailable as exc:
                diagnostics.append(str(exc))
        elif isinstance(brief, str) and brief.strip():
            diagnostics.append("NLI provider unavailable; explicit brief fidelity was not scored")
        observations = []
        if variance > float(config.get("line_variance", 20.0)):
            observations.append("Line lengths vary substantially")
        if contamination:
            observations.append("Production vocabulary appears in lyric lines")
        if not any("chorus" in name.casefold() for name in sections):
            observations.append("No labelled chorus was detected")
        return _result(self.capability, {"sections": {name: len(lines) for name, lines in sections.items()},
                                        "line_count": len(all_lines), "mean_words_per_line": mean,
                                        "line_length_variance": variance, "repeated_lines": repetitions,
                                        "brief_contamination": contamination, "section_redundancy": redundancies,
                                        "semantic_section_comparison": model_section_scores, "brief_fidelity": brief_fidelity,
                                        "observations": observations}, candidates=len(observations), diagnostics=diagnostics,
                       verification=verification, cache_hits=cache_hits, cache_misses=cache_misses)


class IssueTriage:
    capability = "runtime.issue-triage"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        logs = context.request.inputs.get("logs", "")
        if isinstance(logs, list):
            lines = [str(item) for item in logs]
        else:
            lines = str(logs).splitlines()
        normalized = []
        for line in lines:
            cooked = re.sub(r"0x[0-9a-f]+", "<addr>", line, flags=re.I)
            cooked = re.sub(r"\b\d{4}-\d\d-\d\d[T ][0-9:.+Z-]+", "<time>", cooked)
            cooked = re.sub(r"\bpid[=: ]+\d+", "pid=<id>", cooked, flags=re.I)
            cooked = re.sub(r"\b\d+\.\d+ms\b", "<duration>", cooked, flags=re.I)
            if cooked.strip():
                normalized.append(cooked.strip())
        groups: dict[str, dict[str, Any]] = {}
        for line in normalized:
            fingerprint = sha256_bytes(line.encode())[:16]
            group = groups.setdefault(fingerprint, {"fingerprint": fingerprint, "example": line[:240], "count": 0})
            group["count"] += 1
        rules = {
            "network": r"timeout|connection|dns|socket|http\s*[45]\d\d",
            "dependency": r"module not found|importerror|dependency|package|version conflict",
            "filesystem": r"permission denied|access denied|not found|no such file|path",
            "memory": r"out of memory|oom|allocation|heap",
            "test": r"assert|expected|test failed|failure",
            "runtime": r"exception|traceback|stack trace|crash|fatal",
        }
        joined = "\n".join(normalized)
        subsystem_scores = {name: float(len(re.findall(pattern, joined, re.I))) for name, pattern in rules.items()}
        ranked = sorted(subsystem_scores, key=subsystem_scores.get, reverse=True)
        actions = {
            "network": "Verify endpoint health, DNS resolution, and timeout boundaries",
            "dependency": "Compare the installed dependency graph with the lockfile",
            "filesystem": "Verify the resolved path and effective permissions",
            "memory": "Measure peak allocation and reproduce with the smallest input",
            "test": "Run the narrow failing test with structured output",
            "runtime": "Locate the first application frame in the earliest stack trace",
        }
        likely = [{"subsystem": name, "rule_hits": subsystem_scores[name], "next_diagnostic": actions[name]}
                  for name in ranked if subsystem_scores[name] > 0]
        historical: list[dict[str, Any]] = []
        diagnostics: list[str] = []
        verification: list[dict[str, Any]] = []
        cache, cache_hits, cache_misses = _cache(context), 0, 0
        supplied_history = context.request.inputs.get("history", [])
        if supplied_history:
            history_docs = []
            for index, item in enumerate(supplied_history):
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    history_docs.append((str(item.get("path", f"history:{index}")), item["text"], None))
            historical, diagnostics, history_hits, history_misses, history_verification = _rank_context(context, joined, history_docs, int(config.get("history_limit", 5)))
            cache_hits += history_hits
            cache_misses += history_misses
            verification.extend(history_verification)
        classifier = _provider(context, "classification", ClassificationProvider)
        if classifier and normalized:
            try:
                verification.append(provider_identity(classifier))
                model_text = joined[:8000]
                key = cache.key("issue-classify", provider_identity(classifier), {"text": sha256_bytes(model_text.encode()), "labels": list(rules)})
                model_rows = cache.get(key)
                if model_rows is None:
                    cache_misses += 1
                    model_rows = classifier.classify(ClassificationRequest(texts=[model_text], labels=list(rules))).scores
                    cache.set(key, model_rows)
                else:
                    cache_hits += 1
                if model_rows:
                    for item in likely:
                        item["model_score"] = float(model_rows[0].get(item["subsystem"], 0.0))
            except ProviderUnavailable as exc:
                diagnostics.append(str(exc))
        elif normalized:
            diagnostics.append("Classification provider unavailable; issue routing used deterministic fingerprints and rules")
        return _result(self.capability, {"groups": sorted(groups.values(), key=lambda x: x["count"], reverse=True),
                                        "likely_subsystems": likely, "historical_matches": historical,
                                        "definitive_root_cause": None},
                       scores={f"subsystem.{name}": value for name, value in subsystem_scores.items()},
                       candidates=len(groups), diagnostics=diagnostics, verification=verification,
                       cache_hits=cache_hits, cache_misses=cache_misses)


def register_generic_capabilities(registry: CapabilityRegistry) -> None:
    for primitive in (
        ValidateScopedDelta, ChangePacket, RepoPreflight, RetrieveContext, SemanticDuplicate,
        ClassifyArtifact, ClaimEvidenceReview, SessionContextPacket, LyricAudit, IssueTriage,
    ):
        registry.register(primitive.capability, primitive)

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ...contracts import EvidenceReference, PrimitiveMetrics, PrimitiveResult, Provenance
from ...engine import CapabilityUnavailable, ExecutionContext
from ...registry import CapabilityRegistry
from ...services import FoundryManager, FoundryServiceError
from . import analysis, level1


VERSION = "1.0.0"


def _result(capability: str, data: dict[str, Any], *, metrics: PrimitiveMetrics | None = None,
            evidence: list[EvidenceReference] | None = None, provenance: Provenance | None = None) -> PrimitiveResult:
    return PrimitiveResult(
        capability=capability,
        version=VERSION,
        status="success",
        data=data,
        evidence=evidence or [],
        metrics=metrics or PrimitiveMetrics(),
        provenance=provenance or Provenance(implementation=__name__, version=VERSION),
    )


class InventoryPrimitive:
    capability = "workspace.memory.inventory"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        documents = level1.collect_documents(context.workspace)
        chunks = analysis.chunk_documents(
            documents,
            int(config.get("max_chunk_tokens", 180)),
            int(config.get("chunk_overlap", 30)),
            int(config.get("min_chunk_tokens", 30)),
        )
        context.state.update(documents=documents, chunks=chunks, findings=[], signals={})
        return _result(self.capability, {"documents": len(documents), "chunks": len(chunks)})


class StructuralPrimitive:
    capability = "workspace.memory.structural"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        documents, findings = level1.validate(context.workspace)
        context.state["documents"] = documents
        context.state["findings"].extend(findings)
        fatal = sum(item.fatal for item in findings)
        return _result(self.capability, {"fatal_count": fatal, "advisory_count": len(findings) - fatal, "finding_count": len(findings)})


class FreshnessPrimitive:
    capability = "workspace.memory.freshness"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        findings = analysis.freshness_findings(context.state["documents"], context.workspace)
        context.state["findings"].extend(findings)
        return _result(self.capability, {"finding_count": len(findings)}, metrics=PrimitiveMetrics(candidate_count=len(findings)))


class RelationshipGraphPrimitive:
    capability = "workspace.memory.relationship-graph"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        documents = context.state["documents"]
        relationships = analysis.relationship_pairs(documents, context.workspace)
        cochange = analysis.cochange_pairs(documents, context.workspace)
        eligible = [document for document in documents if analysis.eligible_document(document) in {"governed", "skill"}]
        git_documents = sum(level1.repository_root(document.path, context.workspace) is not None for document in eligible)
        findings = analysis.cochange_findings(cochange, relationships)
        context.state.update(relationships=relationships, cochange=cochange)
        context.state["findings"].extend(findings)
        return _result(self.capability, {
            "relationships": len(relationships), "cochange_pairs": len(cochange), "finding_count": len(findings),
            "cochange_signal": {
                "status": "available" if git_documents else "unavailable",
                "git_documents": git_documents,
                "unavailable_documents": len(eligible) - git_documents,
            },
        }, metrics=PrimitiveMetrics(candidate_count=len(findings)))


class LexicalSimilarityPrimitive:
    capability = "workspace.memory.lexical-similarity"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        signals = analysis.lexical_signals(context.state["chunks"], context.state.get("relationships", set()))
        context.state["signals"] = signals
        return _result(self.capability, {"pair_count": len(signals)}, metrics=PrimitiveMetrics(candidate_count=len(signals)))


class SemanticSimilarityPrimitive:
    capability = "workspace.memory.semantic-similarity"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        chunks: list[analysis.Chunk] = context.state["chunks"]
        model_id = str(config.get("model_id", "all-MiniLM-L6-v2"))
        preferred_port = int(config.get("preferred_port", 8123))
        adapter_path = context.workspace / "Tools" / "foundry-local-runtime" / "ONNX host service" / "models" / model_id / "adapter.json"
        try:
            adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CapabilityUnavailable(
                f"Embedding model '{model_id}' is not installed or has invalid metadata",
                "Run pwsh -File Tools/foundry-local-runtime/scripts/Install-MiniLM.ps1",
            ) from exc
        model_identity = json.dumps({
            "model": model_id,
            "revision": adapter.get("revision"),
            "sha256": adapter.get("model_sha256"),
            "pooling": adapter.get("pooling"),
            "max_length": adapter.get("max_length"),
        }, sort_keys=True, separators=(",", ":"))
        cache = analysis.EmbeddingCache(context.workspace / "tmp" / "memory-validation" / "embeddings.sqlite3")
        vectors: list[np.ndarray | None] = []
        misses: list[int] = []
        try:
            for index, chunk in enumerate(chunks):
                vector = cache.get(cache.key(chunk, model_identity))
                vectors.append(vector)
                if vector is None:
                    misses.append(index)
            service_info: dict[str, Any] = {}
            if misses:
                manager = FoundryManager(context.workspace, record_telemetry=not bool(context.request.inputs.get("no_write", False)))
                try:
                    for offset in range(0, len(misses), int(config.get("batch_size", 32))):
                        indexes = misses[offset:offset + int(config.get("batch_size", 32))]
                        batch, service_info = manager.embed([chunks[index].text for index in indexes], model_id, preferred_port)
                        for index, raw in zip(indexes, batch):
                            vector = np.asarray(raw, dtype=np.float32)
                            vectors[index] = vector
                            cache.put(cache.key(chunks[index], model_identity), vector)
                except FoundryServiceError as exc:
                    raise CapabilityUnavailable(str(exc), "Run tiny-minds doctor --json and inspect the Foundry service state") from exc
            cooked = np.vstack([vector for vector in vectors if vector is not None])
            if len(cooked) != len(chunks):
                raise CapabilityUnavailable("Not all section embeddings could be produced")
            analysis.add_embedding_signals(context.state["signals"], chunks, cooked)
        finally:
            cache.close()
        provenance = Provenance(
            implementation=__name__, version=VERSION, model_id=model_id,
            model_revision=adapter.get("revision"), model_sha256=adapter.get("model_sha256"),
            verification=[{"foundry_base_url": service_info.get("base_url"), "managed": service_info.get("managed")}],
        )
        return _result(self.capability, {"embedded_chunks": len(chunks), "model_id": model_id},
                       metrics=PrimitiveMetrics(cache_hits=len(chunks) - len(misses), cache_misses=len(misses)), provenance=provenance)


class CandidateRoutingPrimitive:
    capability = "workspace.memory.route-candidates"
    version = VERSION

    DEFAULT_THRESHOLDS = {
        "governed_embedding": 0.82, "governed_bm25": 0.75,
        "generative_embedding": 0.90, "generative_bm25": 0.85,
        "promotion_embedding": 0.88, "support_embedding": 0.84, "support_bm25": 0.80,
    }

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        thresholds = {**self.DEFAULT_THRESHOLDS, **config.get("thresholds", {})}
        findings = analysis.similarity_findings(context.state["signals"], thresholds, context.state.get("cochange", {}))
        max_candidates = context.manifest.budgets.max_candidates
        if len(findings) > max_candidates:
            findings = findings[:max_candidates]
        context.state["findings"].extend(findings)
        evidence: list[EvidenceReference] = []
        for finding in findings[:100]:
            evidence.extend([
                EvidenceReference(
                    path=finding.paths[0], heading=finding.evidence.get("section_a"),
                    chunk_id=finding.evidence.get("chunk_a"), content_sha256=finding.evidence.get("content_sha256_a"),
                    excerpt=finding.evidence.get("excerpt_a"),
                ),
                EvidenceReference(
                    path=finding.paths[1], heading=finding.evidence.get("section_b"),
                    chunk_id=finding.evidence.get("chunk_b"), content_sha256=finding.evidence.get("content_sha256_b"),
                    excerpt=finding.evidence.get("excerpt_b"),
                ),
            ])
        candidates = [finding.as_dict() for finding in findings]
        return _result(self.capability, {"finding_count": len(findings), "candidates": candidates},
                       metrics=PrimitiveMetrics(candidate_count=len(findings)), evidence=evidence)


class ReportPrimitive:
    capability = "workspace.memory.report"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        findings: list[level1.Finding] = context.state["findings"]
        fatal = sum(item.fatal for item in findings)
        no_write = bool(context.request.inputs.get("no_write", False))
        appended_count = 0
        unresolved_count = None
        if not no_write:
            reports = context.manifest.reports
            if reports is None:
                raise ValueError("Memory-validation pipeline requires report paths")
            events = context.workspace / reports.events
            outstanding = context.workspace / reports.outstanding
            appended, unresolved = level1.append_findings(findings, context.workspace, events)
            level1.write_outstanding(outstanding, unresolved, {item.finding_id for item in findings})
            appended_count = len(appended)
            unresolved_count = len(unresolved)
        context.state["fatal_count"] = fatal
        return _result(self.capability, {
            "documents_scanned": len(context.state["documents"]),
            "fatal_count": fatal,
            "advisory_count": len(findings) - fatal,
            "finding_count": len(findings),
            "findings": [finding.as_dict() for finding in findings],
            "events_appended": appended_count,
            "unresolved_count": unresolved_count,
            "no_write": no_write,
        }, metrics=PrimitiveMetrics(candidate_count=len(findings)))


def register_workspace_memory(registry: CapabilityRegistry) -> None:
    for primitive in (
        InventoryPrimitive, StructuralPrimitive, FreshnessPrimitive, RelationshipGraphPrimitive,
        LexicalSimilarityPrimitive, SemanticSimilarityPrimitive, CandidateRoutingPrimitive, ReportPrimitive,
    ):
        registry.register(primitive.capability, primitive)

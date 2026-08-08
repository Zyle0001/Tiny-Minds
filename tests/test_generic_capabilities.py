from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tiny_minds.application import build_registry
from tiny_minds.contracts import ArtifactRef, BoundedContextPacket, RunRequest
from tiny_minds.engine import PipelineApplication
from tiny_minds.manifest import PipelineManifest
from tiny_minds.providers import (
    ClassificationRequest, ClassificationResponse, EmbeddingRequest, EmbeddingResponse,
    NliRequest, NliResponse, NliScores, ProviderRegistry, RerankRequest, RerankResponse,
)


class FakeModels:
    provider_id = "fake"

    def __init__(self, revision: str = "r1") -> None:
        self.calls = {"embed": 0, "rerank": 0, "nli": 0, "classify": 0}
        self.revision = revision

    def cache_identity(self, model_id=None):
        return {"provider_id": self.provider_id, "model_id": model_id or "fake", "model_revision": self.revision, "model_sha256": self.revision}

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self.calls["embed"] += 1
        return EmbeddingResponse(vectors=[[float("alpha" in text), float("beta" in text), 0.1] for text in request.texts])

    def rerank(self, request: RerankRequest) -> RerankResponse:
        self.calls["rerank"] += 1
        query = set(request.query.casefold().split())
        return RerankResponse(scores=[len(query & set(item.casefold().split())) / max(1, len(query)) for item in request.documents])

    def nli(self, request: NliRequest) -> NliResponse:
        self.calls["nli"] += 1
        rows = []
        for pair in request.pairs:
            contradiction = 0.9 if " not " in f" {pair.premise.casefold()} " else 0.05
            rows.append(NliScores(contradiction=contradiction, entailment=0.9 if contradiction < 0.5 else 0.05, neutral=0.05))
        return NliResponse(scores=rows)

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        self.calls["classify"] += 1
        return ClassificationResponse(scores=[{label: float(label.casefold() in text.casefold()) for label in request.labels} for text in request.texts])


def manifest(capability: str, *, dependencies: bool = False) -> PipelineManifest:
    nodes = [{"id": "node", "capability": capability}]
    if dependencies:
        nodes = [
            {"id": "preflight", "capability": "repo.preflight"},
            {"id": "changes", "capability": "workspace.change-packet"},
            {"id": "retrieve", "capability": "workspace.retrieve-context"},
            {"id": "node", "capability": capability, "depends_on": ["preflight", "changes", "retrieve"]},
        ]
    return PipelineManifest.model_validate({
        "schema_version": 1, "id": capability, "version": "0.2.0",
        "integrations": ["generic-workspace"], "nodes": nodes,
    })


def providers() -> ProviderRegistry:
    result = ProviderRegistry()
    fake = FakeModels()
    for provider_id in ("embeddings", "reranker", "nli", "classification"):
        result.register(provider_id, fake)
    return result


def run(tmp_path: Path, capability: str, inputs: dict, *, models: bool = True, dependencies: bool = False):
    return PipelineApplication(build_registry(["generic-workspace"]), providers() if models else ProviderRegistry()).run(
        manifest(capability, dependencies=dependencies), RunRequest(inputs=inputs), tmp_path
    )


def test_portable_contract_round_trips() -> None:
    artifact = ArtifactRef(uri="note.md", media_type="text/markdown", content_sha256="a" * 64, size_bytes=1)
    assert ArtifactRef.model_validate_json(artifact.model_dump_json()) == artifact
    packet = BoundedContextPacket(output_bytes=10)
    assert packet.model_dump()["output_bytes"] == 10


def test_scoped_delta_enforces_allowlist_without_writes(tmp_path: Path) -> None:
    result = run(tmp_path, "workspace.validate-scoped-delta", {
        "before": {"owned/report.md": "1", "source.md": "1"},
        "after": {"owned/report.md": "2", "source.md": "2"}, "allowed": ["owned/**"],
    })
    assert result.primitives["node"].data["valid"] is False
    assert result.primitives["node"].data["violations"][0]["path"] == "source.md"
    assert list(tmp_path.iterdir()) == []


def test_repo_change_packet_and_preflight(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    result = run(tmp_path, "repo.preflight", {"repository": str(tmp_path)})
    assert result.primitives["node"].data["ready"] is True
    assert result.primitives["node"].data["dirty"] is True
    packet = run(tmp_path, "workspace.change-packet", {"repository": str(tmp_path)})
    assert packet.primitives["node"].data["changes"][0]["status"] == "untracked"


def test_retrieval_degrades_cleanly_without_models(tmp_path: Path) -> None:
    inputs = {"query": "alpha memory", "documents": [
        {"path": "a.md", "text": "alpha memory validation"},
        {"path": "b.md", "text": "unrelated music"},
    ]}
    result = run(tmp_path, "workspace.retrieve-context", inputs, models=False)
    assert result.status == "partial"
    assert result.primitives["node"].data["results"][0]["path"] == "a.md"
    assert result.primitives["node"].diagnostics


def test_retrieval_and_duplicate_use_separate_scores(tmp_path: Path) -> None:
    inputs = {"query": "alpha", "documents": [{"path": "a.md", "text": "alpha"}, {"path": "b.md", "text": "beta"}]}
    retrieved = run(tmp_path, "workspace.retrieve-context", inputs)
    scores = retrieved.primitives["node"].data["results"][0]["scores"]
    assert set(scores) == {"lexical", "embedding", "reranker"}
    duplicate = run(tmp_path, "workspace.semantic-duplicate", {"target": "alpha", "documents": inputs["documents"]})
    assert duplicate.primitives["node"].data["exact_duplicate"] is True


def test_warm_retrieval_uses_cache_without_provider_requests(tmp_path: Path) -> None:
    fake = FakeModels()
    registry = ProviderRegistry()
    for provider_id in ("embeddings", "reranker"):
        registry.register(provider_id, fake)
    application = PipelineApplication(build_registry(["generic-workspace"]), registry)
    request = RunRequest(inputs={"query": "alpha", "documents": [{"path": "a.md", "text": "alpha memory"}]})
    first = application.run(manifest("workspace.retrieve-context"), request, tmp_path)
    first_calls = dict(fake.calls)
    second = application.run(manifest("workspace.retrieve-context"), request, tmp_path)
    assert fake.calls == first_calls
    assert first.primitives["node"].metrics.cache_misses == 2
    assert second.primitives["node"].metrics.cache_hits == 2


def test_cache_invalidates_when_model_revision_changes(tmp_path: Path) -> None:
    request = RunRequest(inputs={"query": "alpha", "documents": [{"path": "a.md", "text": "alpha memory"}]})
    for revision in ("r1", "r2"):
        fake = FakeModels(revision)
        registry = ProviderRegistry()
        for provider_id in ("embeddings", "reranker"):
            registry.register(provider_id, fake)
        result = PipelineApplication(build_registry(["generic-workspace"]), registry).run(
            manifest("workspace.retrieve-context"), request, tmp_path
        )
        assert result.primitives["node"].metrics.cache_misses == 2


def test_all_model_backed_generic_stages_are_warm_cached(tmp_path: Path) -> None:
    fake = FakeModels()
    registry = ProviderRegistry()
    for provider_id in ("embeddings", "reranker", "nli", "classification"):
        registry.register(provider_id, fake)
    application = PipelineApplication(build_registry(["generic-workspace"]), registry)
    cases = [
        ("workspace.classify-artifact", {"text": "design", "path": "a.md", "taxonomy": {"design": "design", "music": "music"}}),
        ("text.claim-evidence-review", {"pairs": [{"claim": "alpha", "evidence": "alpha"}]}),
        ("creative.lyric-audit", {"lyrics": "[Verse]\nalpha line\n[Chorus]\nbeta line", "brief": "alpha"}),
        ("runtime.issue-triage", {"logs": "connection timeout"}),
    ]
    for capability, inputs in cases:
        request = RunRequest(inputs=inputs)
        application.run(manifest(capability), request, tmp_path)
        calls = dict(fake.calls)
        second = application.run(manifest(capability), request, tmp_path)
        assert fake.calls == calls
        assert second.primitives["node"].metrics.cache_hits > 0


def test_classification_claim_lyric_and_issue_capabilities(tmp_path: Path) -> None:
    classified = run(tmp_path, "workspace.classify-artifact", {
        "path": "design.md", "text": "This is a design document",
        "taxonomy": {"design": {"description": "design", "extensions": [".md"]}, "audio": "music audio"},
    })
    assert classified.primitives["node"].data["alternatives"][0]["label"] == "design"
    reviewed = run(tmp_path, "text.claim-evidence-review", {"pairs": [{"claim": "The server is healthy", "evidence": "The server is healthy"}]})
    assert reviewed.primitives["node"].data["relationships"][0]["relation"] == "supported"
    lyric = run(tmp_path, "creative.lyric-audit", {"lyrics": "[Verse]\nSame line\nSame line\n[Chorus]\nHold on"})
    assert lyric.primitives["node"].data["repeated_lines"]["same line"] == 2
    triage = run(tmp_path, "runtime.issue-triage", {"logs": "Connection timeout\nConnection timeout"})
    assert triage.primitives["node"].data["likely_subsystems"][0]["subsystem"] == "network"


def test_session_packet_composes_dependencies(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    result = run(tmp_path, "session.context-packet", {
        "repository": str(tmp_path), "query": "goal", "documents": [{"path": "Goals.md", "text": "current goal"}],
    }, dependencies=True)
    assert result.primitives["node"].data["items"]


@pytest.mark.parametrize("capability", [
    "workspace.validate-scoped-delta", "workspace.change-packet", "repo.preflight",
    "workspace.retrieve-context", "workspace.semantic-duplicate", "workspace.classify-artifact",
    "text.claim-evidence-review", "session.context-packet", "creative.lyric-audit", "runtime.issue-triage",
])
def test_all_ten_capabilities_are_registered(capability: str) -> None:
    assert capability in build_registry(["generic-workspace"]).capabilities()

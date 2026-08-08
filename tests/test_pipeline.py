from __future__ import annotations

import hashlib
from pathlib import Path

from tiny_minds.application import execute_pipeline
from tiny_minds.contracts import RunRequest
from tiny_minds.integrations.workspace_memory import level1
from tiny_minds.manifest import PipelineManifest


def source_hashes(workspace: Path) -> dict[str, str]:
    return {
        path.relative_to(workspace).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in workspace.rglob("*")
        if path.is_file() and "tmp" not in path.relative_to(workspace).parts
    }


def memory_manifest() -> PipelineManifest:
    capabilities = [
        ("inventory", "workspace.memory.inventory", [], True),
        ("structural", "workspace.memory.structural", ["inventory"], True),
        ("freshness", "workspace.memory.freshness", ["structural"], True),
        ("relationships", "workspace.memory.relationship-graph", ["freshness"], True),
        ("lexical", "workspace.memory.lexical-similarity", ["relationships"], True),
        ("semantic", "workspace.memory.semantic-similarity", ["lexical"], False),
        ("route", "workspace.memory.route-candidates", ["lexical", "semantic"], True),
        ("report", "workspace.memory.report", ["route"], True),
    ]
    return PipelineManifest.model_validate({
        "schema_version": 1,
        "id": "memory-validation",
        "version": "1-test",
        "integrations": ["workspace-memory"],
        "budgets": {"timeout_seconds": 30, "max_candidates": 100, "max_output_bytes": 500_000},
        "reports": {"events": "Reports/events.jsonl", "outstanding": "Reports/Outstanding.md"},
        "nodes": [
            {"id": node_id, "capability": capability, "depends_on": dependencies, "required": required,
             "config": {"min_chunk_tokens": 1} if node_id == "inventory" else {}}
            for node_id, capability, dependencies, required in capabilities
        ],
    })


def test_full_pipeline_degrades_without_foundry_or_model_and_does_not_mutate_sources(tmp_path: Path) -> None:
    for domain in level1.DOMAINS:
        (tmp_path / domain).mkdir(parents=True)
    (tmp_path / "README.md").write_text("# Workspace\n", encoding="utf-8")
    (tmp_path / "Ideas" / "Draft.md").write_text(
        "# Draft\n\nA small local thought with enough words to become a deterministic lexical chunk.\n",
        encoding="utf-8",
    )
    before = source_hashes(tmp_path)
    result = execute_pipeline(memory_manifest(), RunRequest(inputs={"no_write": True}), tmp_path)
    after = source_hashes(tmp_path)
    assert result.status == "partial"
    assert result.primitives["semantic"].status == "unavailable"
    assert result.primitives["report"].status == "success"
    assert result.primitives["semantic"].remediation
    assert result.primitives["relationships"].data["cochange_signal"]["status"] == "unavailable"
    assert before == after
    assert not (tmp_path / "Reports").exists()

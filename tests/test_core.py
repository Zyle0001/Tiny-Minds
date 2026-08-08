from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tiny_minds.application import execute_pipeline
from tiny_minds.contracts import EvidenceReference, PrimitiveMetrics, PrimitiveResult, Provenance, RunRequest
from tiny_minds.engine import PipelineApplication, PipelineExecutionError
from tiny_minds.manifest import PipelineManifest
from tiny_minds.registry import CapabilityRegistry


class RecordingPrimitive:
    capability = "test.record"
    version = "1"

    def __init__(self, calls: list[str], candidates: int = 0) -> None:
        self.calls = calls
        self.candidates = candidates

    def execute(self, context, config, dependencies):
        self.calls.append(config["name"])
        return PrimitiveResult(
            capability=self.capability,
            version=self.version,
            status="success",
            data={"enabled": config.get("enabled", True)},
            metrics=PrimitiveMetrics(candidate_count=self.candidates),
            provenance=Provenance(implementation=__name__, version="1"),
        )


def manifest(nodes: list[dict], integrations: list[str] | None = None, **budgets) -> PipelineManifest:
    return PipelineManifest.model_validate({
        "schema_version": 1,
        "id": "test",
        "version": "1",
        "integrations": integrations or [],
        "nodes": nodes,
        "budgets": {"timeout_seconds": 5, "max_candidates": 50, "max_output_bytes": 100_000, **budgets},
    })


def test_contract_round_trip_and_schema_rejection() -> None:
    request = RunRequest(inputs={"value": 1})
    assert RunRequest.model_validate_json(request.model_dump_json()) == request
    with pytest.raises(ValidationError):
        RunRequest.model_validate({"schema_version": 2})
    with pytest.raises(ValidationError):
        EvidenceReference(path="x.md", excerpt="x" * 241)


def test_registry_uniqueness_and_unknown_capability(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    registry.register("test.record", lambda: RecordingPrimitive([]))
    with pytest.raises(ValueError, match="already registered"):
        registry.register("test.record", lambda: RecordingPrimitive([]))
    with pytest.raises(ValueError, match="unregistered"):
        PipelineApplication(registry).run(
            manifest([{"id": "bad", "capability": "arbitrary.shell"}]), RunRequest(), tmp_path
        )


def test_dag_ordering_and_condition_evaluation(tmp_path: Path) -> None:
    calls: list[str] = []
    registry = CapabilityRegistry()
    registry.register("test.record", lambda: RecordingPrimitive(calls))
    result = PipelineApplication(registry).run(
        manifest([
            {"id": "first", "capability": "test.record", "config": {"name": "first", "enabled": True}},
            {"id": "second", "capability": "test.record", "depends_on": ["first"], "config": {"name": "second"}},
            {"id": "skipped", "capability": "test.record", "depends_on": ["first"],
             "when": {"node": "first", "path": "data.enabled", "operator": "falsy"}, "config": {"name": "skipped"}},
        ]), RunRequest(), tmp_path
    )
    assert calls == ["first", "second"]
    assert result.primitives["skipped"].status == "skipped"


def test_manifest_rejects_cycles_unknown_dependencies_and_extra_execution_fields() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        manifest([
            {"id": "a", "capability": "test.record", "depends_on": ["b"]},
            {"id": "b", "capability": "test.record", "depends_on": ["a"]},
        ])
    with pytest.raises(ValidationError, match="unknown dependencies"):
        manifest([{"id": "a", "capability": "test.record", "depends_on": ["missing"]}])
    with pytest.raises(ValidationError):
        manifest([{"id": "a", "capability": "test.record", "shell": "whoami"}])


def test_candidate_and_output_budgets_are_enforced(tmp_path: Path) -> None:
    registry = CapabilityRegistry()
    registry.register("test.record", lambda: RecordingPrimitive([], candidates=2))
    with pytest.raises(PipelineExecutionError, match="max_candidates"):
        PipelineApplication(registry).run(
            manifest([{"id": "a", "capability": "test.record", "enforce_candidate_budget": True,
                       "config": {"name": "a"}}], max_candidates=1),
            RunRequest(), tmp_path,
        )
    with pytest.raises(PipelineExecutionError, match="max_output_bytes"):
        PipelineApplication(registry).run(
            manifest([{"id": "a", "capability": "test.record", "config": {"name": "a"}}], max_output_bytes=10),
            RunRequest(), tmp_path,
        )


def test_application_service_accepts_objects_without_subprocess(tmp_path: Path) -> None:
    result = execute_pipeline(manifest([]), {"schema_version": 1, "inputs": {}}, tmp_path)
    payload = json.loads(result.model_dump_json())
    assert payload["pipeline"] == {"id": "test", "version": "1"}
    assert payload["status"] == "success"


def test_application_cancellation_is_checked_before_execution(tmp_path: Path) -> None:
    with pytest.raises(PipelineExecutionError, match="cancelled"):
        execute_pipeline(
            manifest([{"id": "hash", "capability": "core.hash.sha256", "config": {"value": "x"}}]),
            RunRequest(), tmp_path, cancel_check=lambda: True,
        )


def test_core_deterministic_primitives_and_absent_provider(tmp_path: Path) -> None:
    portable = manifest([
        {"id": "hash", "capability": "core.hash.sha256", "config": {"input_key": "value"}},
        {"id": "structure", "capability": "core.structure.validate-mapping",
         "config": {"input_key": "document", "required": ["id", "kind"]}},
        {"id": "retrieve", "capability": "workspace.retrieve-context"},
    ], integrations=["generic-workspace"])
    result = execute_pipeline(
        portable,
        {"schema_version": 1, "inputs": {
            "value": "portable", "document": {"id": 1, "kind": "test"},
            "query": "portable", "documents": [{"path": "proof.md", "text": "portable proof"}],
            "no_write": True,
        }},
        tmp_path,
    )
    assert result.status == "partial"
    assert result.primitives["hash"].status == "success"
    assert len(result.primitives["hash"].data["digest"]) == 64
    assert result.primitives["structure"].data["valid"] is True
    assert result.primitives["retrieve"].status == "degraded"
    assert "provider unavailable" in result.primitives["retrieve"].diagnostics[0].lower()

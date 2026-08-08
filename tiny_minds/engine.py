from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import PipelineIdentity, PipelineResult, PrimitiveMetrics, PrimitiveResult, Provenance, RunRequest
from .manifest import Condition, PipelineManifest
from .registry import CapabilityRegistry


class CapabilityUnavailable(RuntimeError):
    def __init__(self, message: str, remediation: str | None = None) -> None:
        super().__init__(message)
        self.remediation = remediation


class PipelineExecutionError(RuntimeError):
    pass


@dataclass
class ExecutionContext:
    workspace: Path
    request: RunRequest
    manifest: PipelineManifest
    state: dict[str, Any] = field(default_factory=dict)


def _value_at(result: PrimitiveResult, path: str) -> Any:
    value: Any = result.model_dump(mode="json")
    for segment in path.split("."):
        if not isinstance(value, dict) or segment not in value:
            return None
        value = value[segment]
    return value


def condition_matches(condition: Condition, results: dict[str, PrimitiveResult]) -> bool:
    result = results.get(condition.node)
    if result is None:
        return False
    actual = _value_at(result, condition.path)
    expected = condition.value
    operations = {
        "eq": lambda: actual == expected,
        "ne": lambda: actual != expected,
        "gt": lambda: actual is not None and actual > expected,
        "gte": lambda: actual is not None and actual >= expected,
        "lt": lambda: actual is not None and actual < expected,
        "lte": lambda: actual is not None and actual <= expected,
        "in": lambda: actual in expected,
        "not_in": lambda: actual not in expected,
        "truthy": lambda: bool(actual),
        "falsy": lambda: not bool(actual),
    }
    return bool(operations[condition.operator]())


def _topological_nodes(manifest: PipelineManifest):
    remaining = {node.id: node for node in manifest.nodes}
    emitted: set[str] = set()
    while remaining:
        ready = [node for node in remaining.values() if set(node.depends_on) <= emitted]
        if not ready:
            raise PipelineExecutionError("Pipeline graph cannot be ordered")
        for node in ready:
            yield node
            emitted.add(node.id)
            del remaining[node.id]


class PipelineApplication:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def run(self, manifest: PipelineManifest, request: RunRequest, workspace: Path) -> PipelineResult:
        unknown = sorted({node.capability for node in manifest.nodes} - set(self.registry.capabilities()))
        if unknown:
            raise ValueError(f"Manifest references unregistered capabilities: {unknown}")
        started = time.perf_counter()
        deadline = started + manifest.budgets.timeout_seconds
        context = ExecutionContext(workspace.resolve(), request, manifest)
        results: dict[str, PrimitiveResult] = {}
        diagnostics: list[str] = []
        partial = False

        for node in _topological_nodes(manifest):
            if time.perf_counter() > deadline:
                raise PipelineExecutionError(f"Pipeline exceeded {manifest.budgets.timeout_seconds}s budget")
            if node.when and not condition_matches(node.when, results):
                results[node.id] = PrimitiveResult(
                    capability=node.capability,
                    version="1",
                    status="skipped",
                    provenance=Provenance(implementation="tiny_minds.engine", version="1"),
                )
                continue
            primitive = self.registry.create(node.capability)
            node_started = time.perf_counter()
            dependencies = {name: results[name] for name in node.depends_on}
            try:
                result = primitive.execute(context, node.config, dependencies)
            except CapabilityUnavailable as exc:
                if node.required:
                    raise PipelineExecutionError(f"Required capability '{node.capability}' unavailable: {exc}") from exc
                partial = True
                result = PrimitiveResult(
                    capability=node.capability,
                    version=getattr(primitive, "version", "1"),
                    status="unavailable",
                    provenance=Provenance(implementation=primitive.__class__.__module__, version=getattr(primitive, "version", "1")),
                    diagnostics=[str(exc)],
                    remediation=exc.remediation,
                )
            except Exception as exc:
                if node.required:
                    raise PipelineExecutionError(f"Capability '{node.capability}' failed: {exc}") from exc
                partial = True
                result = PrimitiveResult(
                    capability=node.capability,
                    version=getattr(primitive, "version", "1"),
                    status="error",
                    provenance=Provenance(implementation=primitive.__class__.__module__, version=getattr(primitive, "version", "1")),
                    diagnostics=[str(exc)],
                )
            result.metrics.duration_ms = int((time.perf_counter() - node_started) * 1000)
            results[node.id] = result
            if node.enforce_candidate_budget and result.metrics.candidate_count > manifest.budgets.max_candidates:
                raise PipelineExecutionError(
                    f"Capability '{node.capability}' produced {result.metrics.candidate_count} candidates, "
                    f"exceeding max_candidates={manifest.budgets.max_candidates}"
                )
            if time.perf_counter() > deadline:
                raise PipelineExecutionError(f"Pipeline exceeded {manifest.budgets.timeout_seconds}s budget")

        disposition = manifest.default_disposition
        for rule in manifest.routing:
            if condition_matches(rule.when, results):
                disposition = rule.disposition
                break
        evidence = []
        for result in results.values():
            evidence.extend(result.evidence)
        pipeline_result = PipelineResult(
            run_id=uuid.uuid4().hex,
            pipeline=PipelineIdentity(id=manifest.id, version=manifest.version),
            status="partial" if partial else "success",
            disposition=disposition,
            primitives=results,
            evidence=evidence,
            diagnostics=diagnostics,
            metrics={
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "candidate_count": sum(item.metrics.candidate_count for item in results.values()),
            },
        )
        encoded = json.dumps(pipeline_result.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
        if len(encoded) > manifest.budgets.max_output_bytes:
            raise PipelineExecutionError("Pipeline result exceeds max_output_bytes budget")
        return pipeline_result

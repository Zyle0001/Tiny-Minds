from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator

from .contracts import ContractModel, SCHEMA_VERSION


class Condition(ContractModel):
    node: str
    path: str
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "truthy", "falsy"]
    value: Any = None


class PipelineNode(ContractModel):
    id: str
    capability: str
    depends_on: list[str] = Field(default_factory=list)
    required: bool = True
    enforce_candidate_budget: bool = False
    when: Condition | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class RoutingRule(ContractModel):
    when: Condition
    disposition: Literal["resolved", "review", "escalate"]


class PipelineBudgets(ContractModel):
    timeout_seconds: float = Field(default=300.0, gt=0)
    max_candidates: int = Field(default=500, gt=0)
    max_output_bytes: int = Field(default=5_000_000, gt=0)


class ReportSink(ContractModel):
    events: str
    outstanding: str


class PipelineManifest(ContractModel):
    schema_version: int
    id: str
    version: str
    integrations: list[Literal["workspace-memory"]] = Field(default_factory=list)
    nodes: list[PipelineNode]
    routing: list[RoutingRule] = Field(default_factory=list)
    default_disposition: Literal["resolved", "review", "escalate"] = "resolved"
    budgets: PipelineBudgets = Field(default_factory=PipelineBudgets)
    reports: ReportSink | None = None

    @model_validator(mode="after")
    def validate_graph(self) -> "PipelineManifest":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported manifest schema_version {self.schema_version}")
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Pipeline node IDs must be unique")
        known = set(ids)
        for node in self.nodes:
            unknown = set(node.depends_on) - known
            if unknown:
                raise ValueError(f"Node '{node.id}' has unknown dependencies: {sorted(unknown)}")
            if node.when and node.when.node not in known:
                raise ValueError(f"Node '{node.id}' condition references unknown node '{node.when.node}'")
        for rule in self.routing:
            if rule.when.node not in known:
                raise ValueError(f"Routing rule references unknown node '{rule.when.node}'")

        visiting: set[str] = set()
        visited: set[str] = set()
        graph = {node.id: node.depends_on for node in self.nodes}

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError(f"Pipeline dependency cycle includes '{node_id}'")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in graph[node_id]:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in ids:
            visit(node_id)
        return self


def load_manifest(path: Path) -> PipelineManifest:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read pipeline manifest '{path}': {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Pipeline manifest '{path}' must contain a mapping")
    return PipelineManifest.model_validate(payload)

# Tiny Minds

Tiny Minds is a portable cognitive-machinery runtime. It replaces broad LLM calls with deterministic checks, hashes, retrieval, graph analysis, embeddings, classifiers, and narrow local models wherever those mechanisms can produce reliable evidence.

Tiny Minds does not call frontier models. A pipeline returns `resolved`, `review`, or `escalate` with bounded evidence so the host agent can decide whether expensive reasoning is necessary.

## Portable Core

The base wheel has no Foundry, `psutil`, NumPy, Agentic Workspace, or fixed filesystem-layout requirement. It provides versioned contracts, DAG execution, deterministic primitives, routing, and an explicit provider registry. An empty provider registry is valid.

```powershell
tiny-minds doctor --json
tiny-minds capabilities --json
tiny-minds run path/to/pipeline.yaml --input path/to/input.json --no-write --json
```

Core capability discovery publishes only `core.hash.sha256`, `core.structure.validate-mapping`, and `core.provider.invoke`. Provider-backed nodes must be optional or supplied an explicit provider; absence returns bounded degradation rather than triggering a fallback.

## Optional Workspace Integration

The workspace-memory and Foundry components are optional integrations, not core requirements:

```powershell
python -m pip install -e ".[workspace-memory,foundry]"
tiny-minds capabilities --integration workspace-memory --json
tiny-minds doctor --integration workspace-memory --workspace "C:\AI Agent Workspace\Agentic Workspace" --json
tiny-minds run memory-validation --workspace "C:\AI Agent Workspace\Agentic Workspace" --json
tiny-minds service status foundry --workspace "C:\AI Agent Workspace\Agentic Workspace" --json
```

All commands emit one JSON document on stdout. Diagnostics use stderr. Pipeline manifests are reviewed YAML DAGs that may invoke only registered capabilities; they cannot execute arbitrary code.

## Architecture

- `tiny_minds/contracts.py` — versioned evidence and result schemas.
- `tiny_minds/manifest.py` — declarative DAG validation.
- `tiny_minds/engine.py` — deterministic execution and routing.
- `tiny_minds/providers.py` — provider-neutral injection contract and empty-provider baseline.
- `tiny_minds/builtins.py` — portable deterministic core primitives.
- `tiny_minds/services/` — isolated service lifecycle adapters.
- `tiny_minds/integrations/workspace_memory/` — the first complete Levels 1–3 proof.

Foundry Local Runtime remains this workspace's ONNX execution substrate. It is injected by the explicit `workspace-memory` integration. The base runtime does not import, discover, or require it. The integration may start its backend on demand only when a reached model node has cache misses. It never starts the UI or downloads models implicitly.

## Authority Boundary

Version 1 is read-only toward source knowledge. It may write only declared reports, metadata-only telemetry, disposable caches, and managed-service state. Findings never authorize their own repair.

## Provenance

The original modular-cognition scaffold is preserved in Git history and tagged `legacy-scaffold` at commit `faef019572f599beaeebaa775ac1963e6734078f`. The current evidence-oriented runtime is a deliberate rebuild of that architectural idea.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
$env:TINY_MINDS_RUN_STERILE_WHEEL="1"
.\.venv\Scripts\python.exe -m pytest tests/test_sterile_wheel.py
```

Licensed under Apache-2.0.

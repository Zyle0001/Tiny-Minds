# Tiny Minds

Tiny Minds is a portable cognitive-machinery runtime. It replaces broad LLM calls with deterministic checks, hashes, retrieval, graph analysis, embeddings, classifiers, and narrow local models wherever those mechanisms can produce reliable evidence.

Tiny Minds does not call frontier models. A pipeline returns `resolved`, `review`, or `escalate` with bounded evidence so the host agent can decide whether expensive reasoning is necessary.

## Interfaces

```powershell
tiny-minds capabilities --json
tiny-minds doctor --workspace "C:\AI Agent Workspace\Agentic Workspace" --json
tiny-minds run memory-validation --workspace "C:\AI Agent Workspace\Agentic Workspace" --json
tiny-minds service status foundry --workspace "C:\AI Agent Workspace\Agentic Workspace" --json
```

All commands emit one JSON document on stdout. Diagnostics use stderr. Pipeline manifests are reviewed YAML DAGs that may invoke only registered capabilities; they cannot execute arbitrary code.

## Architecture

- `tiny_minds/contracts.py` — versioned evidence and result schemas.
- `tiny_minds/manifest.py` — declarative DAG validation.
- `tiny_minds/engine.py` — deterministic execution and routing.
- `tiny_minds/services/` — isolated service lifecycle adapters.
- `tiny_minds/integrations/workspace_memory/` — the first complete Levels 1–3 proof.

Foundry Local Runtime remains the ONNX execution substrate. Tiny Minds may start its backend on demand only when a reached pipeline node requires a model. It never starts the UI or downloads models implicitly.

## Authority Boundary

Version 1 is read-only toward source knowledge. It may write only declared reports, metadata-only telemetry, disposable caches, and managed-service state. Findings never authorize their own repair.

## Provenance

The original modular-cognition scaffold is preserved in Git history and tagged `legacy-scaffold` at commit `faef019572f599beaeebaa775ac1963e6734078f`. The current evidence-oriented runtime is a deliberate rebuild of that architectural idea.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

Licensed under Apache-2.0.

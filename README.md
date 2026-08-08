# Tiny Minds

Tiny Minds is a portable cognitive-machinery runtime. It replaces broad LLM calls with deterministic checks, hashes, retrieval, graph analysis, embeddings, classifiers, and narrow local models wherever those mechanisms can produce reliable evidence.

Tiny Minds does not call frontier models. A pipeline returns `resolved`, `review`, or `escalate` with bounded evidence so the host agent can decide whether expensive reasoning is necessary.

Current maturity: `0.2.0` is a developer preview. The base wheel and separately packaged HTTP-provider extension are portable and sterile-tested; the ten generic capabilities remain experimental until their human-reviewed calibration gates pass. See [STATUS.md](STATUS.md).

## Portable Core

The base wheel has no Foundry, `psutil`, NumPy, Agentic Workspace, or fixed filesystem-layout requirement. It provides versioned contracts, DAG execution, deterministic primitives, routing, and an explicit provider registry. An empty provider registry is valid.

```powershell
tiny-minds doctor --json
tiny-minds capabilities --json
tiny-minds run path/to/pipeline.yaml --input path/to/input.json --no-write --json
```

Core capability discovery publishes only `core.hash.sha256` and `core.structure.validate-mapping`. Selecting `--integration generic-workspace` adds ten workspace-neutral preview capabilities. Provider-backed stages use explicit typed embedding, reranking, NLI, and classification protocols; absence retains deterministic evidence and returns partial degradation.

Provider configuration is versioned YAML selected with `--config`. It contains model identity, revision, checksum, timeouts, batch limits, non-secret settings, and an optional environment-variable name for authentication. Manifests cannot select implementations or contain credentials.

Separately packaged providers and integrations are discovered through `tiny_minds.providers` and `tiny_minds.integrations` entry points. The package under `examples/http-provider` proves all four model protocols without Foundry.

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
- `tiny_minds/extensions.py` — allowlisted package entry-point discovery and API negotiation.
- `tiny_minds/generic.py` — portable inventory, chunking, hashing, BM25, Git probes, and cache utilities.
- `tiny_minds/builtins.py` — portable deterministic core primitives.
- `tiny_minds/services/` — isolated service lifecycle adapters.
- `tiny_minds/integrations/workspace_memory/` — the first complete Levels 1–3 proof.

Foundry Local Runtime remains this workspace's reference ONNX substrate. Generic pipelines select it explicitly through provider configuration; `workspace-memory` retains its compatible injected embedding adapter. The base runtime does not import, discover, or require Foundry. A reached uncached model stage may start its backend; discovery and deterministic stages do not. Models are never downloaded implicitly.

## Authority Boundary

Version 0.2 is read-only toward caller-owned material. It may write only declared reports, metadata-only telemetry, disposable caches, and managed-service state. Findings never authorize their own repair.

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

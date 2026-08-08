# Tiny Minds

LLMs are useful, but they are an expensive way to answer questions that a hash, parser, search index, graph walk, or small classifier can settle. Tiny Minds is a Python runtime for moving that work out of the prompt.

```text
input
  -> deterministic checks, retrieval, graphs, and small local models
  -> resolved result or a bounded escalation packet
  -> LLM only when the cheap machinery cannot finish the job
```

Tiny Minds never calls a frontier model. It runs reviewed capability pipelines and returns `resolved`, `review`, or `escalate` with the evidence behind that decision. The host agent remains responsible for anything unresolved.

## Where it stands

`0.2.0` is a developer preview. The runtime, extension API, typed model-provider contracts, and sterile installation path work today. The workspace memory validator is the first end-to-end proof.

Ten more capabilities are implemented, but deliberately remain experimental until their fixture sets have been reviewed and their calibration gates pass:

- change-scope validation, change packets, and repository preflight;
- context retrieval and semantic duplicate detection;
- artifact classification and claim/evidence review;
- session context packets;
- lyric auditing and runtime issue triage.

That distinction matters. Implemented means the machinery runs. Published means there is enough evidence to let agents rely on it. See [STATUS.md](STATUS.md) and [`calibration/`](calibration/) for the current boundary.

The CI matrix builds and tests the wheel on Windows, Linux, and macOS with Python 3.10 and 3.13. Its sterile tests install the core and an external provider into a fresh environment with no Foundry, Agentic Workspace, NumPy, `psutil`, or fixed directory layout.

## Take it for a spin

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

.\.venv\Scripts\tiny-minds.exe doctor --json
.\.venv\Scripts\tiny-minds.exe capabilities --json
.\.venv\Scripts\tiny-minds.exe capabilities --integration generic-workspace --json
```

Run a manifest against JSON input:

```powershell
.\.venv\Scripts\tiny-minds.exe run path\to\pipeline.yaml `
  --workspace path\to\workspace `
  --input path\to\request.json `
  --no-write `
  --json
```

Commands emit one JSON document on stdout. Diagnostics go to stderr, so the CLI can sit behind an MCP adapter or any other host without inventing a second contract.

## What the core provides

- Versioned request, result, evidence, artifact, chunk, change-set, and context-packet schemas.
- Declarative YAML DAGs with cycle checks, fixed operators, budgets, cancellation, and explicit degradation.
- Deterministic hashing and structural validation with no model dependencies.
- Reusable Markdown chunking, BM25 search, Git inspection, graph inputs, and SQLite-backed result caches.
- Allowlisted package entry points for integrations, capabilities, providers, doctor checks, and service controls.
- Typed protocols for embeddings, reranking, NLI, and zero-shot classification.

An empty provider registry is a valid installation. Model-backed nodes degrade visibly when their provider is missing; there is no secret LLM fallback.

## Bring your own model host

Tiny Minds does not download models or dictate where inference runs. Provider configuration names an implementation, endpoint, model revision, checksum, timeout, and batch limit. Authentication is resolved from a host-owned environment reference and is never copied into manifests, evidence, caches, or telemetry.

[`examples/http-provider`](examples/http-provider/) is a separately packaged provider plus a deterministic fake HTTP host. It exercises all four model protocols without Foundry or source changes to Tiny Minds.

Foundry Local Runtime is the reference ONNX host used by this workspace, not a dependency of the base package. The optional adapter can start Foundry when an uncached model node is actually reached, reuse an owned instance, and leave deterministic work alone.

## Hard boundaries

Tiny Minds is intentionally less capable than an agent:

- it cannot call a frontier LLM;
- manifests cannot run arbitrary commands or import untrusted code;
- pipelines do not repair, merge, move, or rewrite caller-owned material;
- exact hashes may resolve identity, while semantic matches remain review findings;
- telemetry contains metadata, never raw content, excerpts, vectors, diffs, logs, or credentials.

Version `0.2.0` may write only declared reports, disposable caches, metadata-only telemetry, and managed-service state.

## Repository map

- [`tiny_minds/contracts.py`](tiny_minds/contracts.py) — public schemas.
- [`tiny_minds/manifest.py`](tiny_minds/manifest.py) — pipeline validation.
- [`tiny_minds/engine.py`](tiny_minds/engine.py) — DAG execution and routing.
- [`tiny_minds/extensions.py`](tiny_minds/extensions.py) — external package discovery.
- [`tiny_minds/providers.py`](tiny_minds/providers.py) — typed provider contracts and configuration.
- [`tiny_minds/generic.py`](tiny_minds/generic.py) — shared inventory, retrieval, Git, and cache machinery.
- [`tiny_minds/integrations/generic_capabilities.py`](tiny_minds/integrations/generic_capabilities.py) — the ten preview capabilities.
- [`tiny_minds/integrations/workspace_memory/`](tiny_minds/integrations/workspace_memory/) — the first complete validation pipeline.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest

$env:TINY_MINDS_RUN_STERILE_WHEEL = "1"
.\.venv\Scripts\python.exe -m pytest tests\test_sterile_wheel.py
```

The original modular-cognition sketch remains in Git history and is tagged `legacy-scaffold` at commit `faef019`. The current runtime is a rebuild of the useful part of that idea: many small, inspectable mechanisms doing work that should never have needed a giant model.

Licensed under Apache-2.0.

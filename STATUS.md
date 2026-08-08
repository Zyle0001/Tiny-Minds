# Tiny Minds Status

Last reviewed: 2026-08-09

## Current Position

Tiny Minds `0.2.0` is a portable developer preview with a mature Agentic Workspace memory validator and ten implemented but uncalibrated generic capabilities. The rebuilt runtime is on GitHub, its public description and README reflect the current architecture, and the hosted test matrix is green. Release documentation is committed, exact-artifact acceptance has passed in a clean environment, and CI uses the current Node 24 action majors. The final release candidate is rebuilt from the maintenance commit before tagging. The generic capabilities are intentionally not bootstrap-published until their gates have human-reviewed evidence.

## Implemented and Verified

- Portable Python 3.10+ base wheel with versioned contracts, safe YAML DAGs, budgets, routing, stable JSON output, and no frontier-model calls.
- Stable artifact, chunk, workspace-scope, change-set, ranked-candidate, and bounded-context schemas.
- Typed embedding, reranking, NLI, and classification providers plus versioned non-secret configuration.
- Allowlisted package entry-point discovery with duplicate rejection and extension API negotiation.
- Generic inventory, Markdown chunking, SHA-256 identities, normalized BM25, Git inspection, cosine comparison, and SQLite response caching.
- Ten generic capabilities: scoped delta, change packet, preflight, retrieval, semantic duplicates, artifact classification, claim/evidence review, session packets, lyric audits, and issue triage.
- Separately packaged HTTP provider and deterministic fake host covering all four provider protocols.
- Sterile acceptance tests proving the base wheel and external provider work without Foundry, Agentic Workspace, NumPy, `psutil`, environment coupling, or a fixed filesystem layout.
- Foundry adapters and endpoints for embeddings, pair reranking, NLI, and zero-shot classification.
- Explicit pinned installers for MiniLM embeddings, MS MARCO MiniLM reranking, and MiniLM2 NLI; execution never downloads models.
- Metadata-only telemetry, bounded excerpts, provider absence degradation, no-write behavior, and cache-hit accounting.
- Cross-platform CI for Python 3.10 and 3.13 on Windows, Linux, and macOS, with matrix fail-fast disabled so every platform reports independently.

## Verification Baseline

- Tiny Minds: 63 normal tests passed, 2 sterile tests skipped by default.
- Sterile acceptance: 2/2 passed when explicitly enabled.
- Hosted CI: all six Windows, Ubuntu, and macOS jobs passed at commit `07d03b0`; every job ran both the normal and sterile suites.
- Provisional release build: core and example-provider wheels and source distributions built successfully, SHA-256 records generated, and the exact wheels passed a local no-network install, import, doctor, provider-discovery, and capability-discovery smoke test.
- Clean artifact acceptance: the exact core and example-provider wheels installed as `0.2.0` under Python 3.13 with no NumPy, `psutil`, Foundry, or workspace coupling; doctor, discovery, deterministic execution, provider-absence degradation, and live external-provider execution all passed.
- CI actions: `actions/checkout@v7` and `actions/setup-python@v7`, both on Node 24, with the workflow token restricted to `contents: read`.
- Foundry Local Runtime: 5/5 tests passed.
- Existing workspace-memory identities and behavior remain covered by the unchanged regression suite.

## Deliberately Not Published

The seed fixtures are synthetic and are not a substitute for the plan's human-reviewed datasets. Consequently:

- no generic capability is listed as bootstrap-available;
- consuming skills do not invoke the preview pipelines automatically;
- calibration thresholds are recorded but not claimed as met;
- no token-saving claim is made;
- the pinned models are installed and live-smoked locally, but the model-backed calibration datasets still require human review.

## Immediate Next Steps

1. Tag `v0.2.0` and publish the verified artifacts through a GitHub Release. PyPI publication is optional for this preview.
2. Begin the deterministic Phase 1 gate defined in [`docs/phase-1-requirements.md`](docs/phase-1-requirements.md).

## Phase 1 Summary

Phase 1 covers only `workspace.validate-scoped-delta`, `workspace.change-packet`, and `repo.preflight`. They are implemented enough for synthetic tests, but they are not yet complete enough to become workspace policy. Required work includes stable finding identities, fuller Git-state coverage, bounded relationship/test/document evidence, publication-hazard probes, human-reviewed fixtures, and proof of zero caller-owned writes.

Passing Phase 1 is the prerequisite for publishing those capabilities in workspace discovery, adding them to consuming skills, and releasing `0.3.0`. Model-backed calibration begins afterward.

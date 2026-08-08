# Tiny Minds Status

Last reviewed: 2026-08-08

## Current Position

Tiny Minds `0.2.0` is a portable developer preview with a mature Agentic Workspace memory validator and ten implemented but uncalibrated generic capabilities. The generic capabilities are intentionally not bootstrap-published until the gates in `calibration/0.2.0/gates.yaml` have human-reviewed evidence.

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
- Cross-platform CI definition for Python 3.10 and 3.13 on Windows, Linux, and macOS.

## Verification Baseline

- Tiny Minds: 63 normal tests passed, 2 sterile tests skipped by default.
- Sterile acceptance: 2/2 passed when explicitly enabled.
- Foundry Local Runtime: 5/5 tests passed.
- Existing workspace-memory identities and behavior remain covered by the unchanged regression suite.

## Deliberately Not Published

The seed fixtures are synthetic and are not a substitute for the plan's human-reviewed datasets. Consequently:

- no generic capability is listed as bootstrap-available;
- consuming skills do not invoke the preview pipelines automatically;
- calibration thresholds are recorded but not claimed as met;
- no token-saving claim is made;
- the pinned models are installed and live-smoked locally, but the model-backed calibration datasets still require human review.

## Recommended Path

1. Human-review and expand the seed fixtures, especially ambiguous and adversarial cases.
2. Run the expanded fixtures through cold, warm, missing-provider, and malformed-provider audits.
3. Record retrieval, duplicate, classification, claim-review, lyric, and issue-triage metrics against the gates.
4. Publish only passing capabilities in `Cognition/Cognition.md` and wire only their consuming skills.
5. Exercise the checked-in CI workflow on hosted Windows, Linux, and macOS runners.
6. Advance releases through the planned pre-1.0 sequence; reserve `1.0.0` for fully calibrated external adoption.

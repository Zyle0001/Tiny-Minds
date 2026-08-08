# Changelog

All notable changes to Tiny Minds are documented in this file.

The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-09

### Added

- Portable Python 3.10+ runtime for declarative, evidence-first capability pipelines.
- Versioned contracts for requests, results, evidence, artifacts, chunks, change sets, ranked candidates, and bounded context packets.
- Safe YAML DAG execution with cycle checks, budgets, cancellation, routing, and explicit degradation.
- Allowlisted extension discovery for integrations, capabilities, providers, doctor checks, and managed services.
- Typed embedding, reranking, natural-language inference, and zero-shot classification provider protocols.
- Generic workspace primitives for inventory, Markdown chunking, SHA-256 identities, BM25 retrieval, Git inspection, cosine comparison, and SQLite caching.
- Ten experimental generic capabilities covering change safety, retrieval, classification, context construction, lyric review, and issue triage.
- Separately packaged example HTTP provider with a deterministic fake host.
- Optional Foundry Local Runtime adapters for embeddings, reranking, NLI, and classification.
- Metadata-only telemetry and bounded evidence excerpts.
- Cross-platform CI on Windows, Linux, and macOS with Python 3.10 and 3.13.
- Sterile acceptance tests for the base wheel and external provider.

### Changed

- Rebuilt the legacy modular-cognition scaffold as a provider-neutral runtime.
- Moved Agentic Workspace memory validation and Foundry support behind explicit optional integrations.
- Adopted a pre-1.0 developer-preview version while capability calibration remains in progress.

### Safety boundaries

- Tiny Minds never calls a frontier model.
- Pipelines cannot execute arbitrary commands or modify caller-owned material.
- Model-backed stages degrade visibly when a configured provider is unavailable.
- Generic capabilities remain experimental until their human-reviewed calibration gates pass.

[0.2.0]: https://github.com/Zyle0001/Tiny-Minds/releases/tag/v0.2.0

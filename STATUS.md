# Tiny Minds Status and Recommended Path

Last reviewed: 2026-08-08

## Current Position

Tiny Minds is a working, provider-neutral foundation with one mature workspace-specific proof. It is not yet a config-only product that an external user can point at an arbitrary workspace and model host.

The base wheel is portable. Extending it currently requires Python development against the runtime APIs.

## Implemented and Verified

### Portable core

- Python 3.10+ package and `tiny-minds` console entrypoint.
- Versioned Pydantic request, primitive-result, evidence, provenance, and pipeline-result contracts.
- Reviewed YAML DAG manifests with dependency ordering, cycle rejection, allowlisted conditions, required/optional nodes, and execution budgets.
- Explicit capability and provider registries with no dynamic execution from manifests.
- Core deterministic primitives for SHA-256 hashing and mapping validation.
- Generic optional-provider invocation with bounded unavailable results and no hidden fallback.
- One JSON document on stdout and stable pipeline exit behavior.
- Direct `PipelineApplication` and `execute_pipeline` seams for future wrappers.

### Portability proof

The sterile-wheel acceptance test builds from a disposable source copy, creates a fresh virtual environment, installs the base wheel, strips relevant environment variables, and runs outside any workspace layout. It verifies:

- no Foundry directory, executable, process, or environment variable;
- no Agentic Workspace directories or relative layout;
- neither `psutil` nor NumPy is installed by the base wheel;
- core doctor and capability discovery succeed;
- deterministic primitives and DAG execution succeed;
- an absent model provider yields explicit partial degradation;
- the test leaves the source tree and build-artifact state unchanged.

### Optional integrations

- `workspace-memory` is an explicit manifest integration and optional NumPy extra.
- Foundry is an injected embedding provider and optional `psutil` extra.
- Foundry model discovery, batching, lifecycle, ownership checks, telemetry, and graceful unavailability remain outside the base execution path.
- A live provider smoke test returned a 384-dimensional MiniLM embedding and then stopped the managed process safely.

### Workspace-memory proof

- Existing Level 1 finding identities, event history, report locations, and wrapper exit behavior are preserved.
- Source freshness, relationship graphs, Git co-change, normalized BM25, MiniLM similarity, SQLite caching, explicit routing, and bounded evidence are implemented.
- Cold, warm, degraded, and idempotent paths are covered.
- The validator remains read-only toward workspace knowledge.

### Workspace adoption

- Capability-first policy in `Cognition/Cognition.md` and bootstrap guidance.
- Canonical `use-tiny-minds` skill with synchronized discovery mirrors.
- Architecture and authority decisions recorded in workspace `DECISIONS.md`.
- Metadata-only execution and service-lifecycle telemetry.

## Not Yet Implemented

### External extension and discovery

- No package entry-point discovery for third-party capabilities, providers, or integrations.
- No public CLI mechanism to select a third-party provider implementation.
- No provider configuration schema for endpoints, model identities, timeouts, authentication references, or adapter settings.
- The generic provider contract uses an untyped `invoke(operation, payload)` boundary rather than calibrated task-specific protocols.
- The manifest integration allowlist currently recognizes only `workspace-memory`.

### Generic workspace support

- The supplied memory integration follows Agentic Workspace domains, memory conventions, exclusions, reports, and source rules.
- There is no configurable generic filesystem inventory/chunking/retrieval integration.
- An external user cannot reproduce the memory pipeline against a different knowledge layout using configuration alone.

### External model-host support

- Foundry is the only implemented model-host adapter.
- No example HTTP embedding provider or separately packaged provider exists.
- No secrets/configuration boundary has yet been specified for third-party host credentials.
- The CLI currently wires Foundry specifically when the workspace-memory integration is selected.

### Distribution maturity

- No cross-platform CI workflow currently proves Windows, Linux, and macOS behavior.
- No separately packaged external integration has validated the extension seam.
- No public installation or migration guide exists for external adopters.
- Version `1.0.0` describes the rebuilt internal contract but overstates external product maturity.

## Recommended Path

### 1. Stabilize the extension SDK

- Replace the generic provider invocation boundary with small typed protocols, beginning with embeddings.
- Define public registration contracts for capabilities, providers, integrations, doctor checks, and optional service controls.
- Discover installed extensions through Python package entry points with explicit allowlisting and duplicate rejection.
- Add version negotiation so incompatible extension contracts fail before execution.

### 2. Add safe configuration

- Define a versioned provider configuration schema for endpoint, model, revision, timeout, and non-secret adapter settings.
- Resolve secrets only through explicit host-owned references; never place credentials in manifests, reports, or telemetry.
- Add CLI flags or a configuration file for choosing provider and integration implementations without importing user code from the pipeline manifest.

### 3. Generalize workspace machinery

- Extract configurable filesystem inventory, include/exclude rules, Markdown chunking, hashing, and report sinks from the Agentic Workspace integration.
- Keep the existing memory conventions as a named policy profile rather than a universal assumption.
- Provide a minimal generic knowledge-workspace example with no Agentic Workspace directories.

### 4. Prove third-party adoption

- Build a separate example package that registers an integration and a fake HTTP embedding provider through the public extension mechanism.
- Install the released Tiny Minds wheel and example package into a sterile environment.
- Exercise doctor, discovery, a custom workspace, deterministic nodes, provider-backed nodes, provider absence, and error contracts exclusively through the CLI.
- Run the acceptance suite on Windows, Linux, and macOS.

### 5. Prepare a public release

- Use a pre-1.0 version until the external extension and adoption tests pass, or explicitly label the current release as an internal developer preview.
- Publish concise installation, extension-author, security, and compatibility documentation.
- Add CI for contracts, wheel builds, sterile installation, optional extras, and external example packages.
- Only then describe Tiny Minds as usable with an arbitrary workspace and model host.

## Next-Milestone Acceptance Gate

The next milestone is complete only when a fresh machine can install a Tiny Minds wheel plus a separately packaged test extension and, without modifying Tiny Minds source code:

1. discover the extension through the CLI;
2. validate its configuration before execution;
3. process an arbitrary temporary knowledge directory;
4. call a non-Foundry fake model host;
5. degrade cleanly when that host is absent;
6. emit the same stable evidence contract without leaking content, vectors, or secrets; and
7. pass on Windows, Linux, and macOS.

Until that gate passes, Tiny Minds should be described as a portable cognitive-machinery foundation with a workspace-specific reference integration.

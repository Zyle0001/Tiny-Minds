# Phase 1: Deterministic Safety Gate

Phase 1 turns three experimental capabilities into dependable safety machinery:

- `workspace.validate-scoped-delta`
- `workspace.change-packet`
- `repo.preflight`

These capabilities do not need a model provider. Their results must be reproducible, explainable from repository state, and incapable of changing the material they inspect. Passing this gate is required before they appear in bootstrap discovery or become mandatory steps in workspace skills.

## Starting point

All three capabilities are registered, runnable, and covered by synthetic tests. That is an implementation baseline, not calibration evidence.

Known gaps at the start of Phase 1:

- Scoped-delta validation accepts caller-supplied path-to-hash maps. It does not yet capture before/after filesystem snapshots or Git states itself, identify renames, or express every violation through a stable finding identity.
- Change packets report current Git status, branch, HEAD, and unstaged numeric diff statistics. They do not yet provide complete staged/unstaged attribution, content hashes, impacted relationships, or a bounded set of relevant tests and documentation.
- Repository preflight detects the repository root, branch state, dirty paths, a small set of root instruction files, first-level nested repositories, and basic language markers. It does not yet cover upstream/default-branch state, deeper instruction scope, release hazards, large or sensitive untracked artifacts, submodules/worktrees, or repository-specific validation policy.
- Existing calibration cases are synthetic seeds and have no human review record.

Phase 1 may change these implementations and their schemas while they remain experimental. It must not weaken the read-only boundary.

## Shared requirements

### Authority and filesystem behavior

- Inspect caller-owned material without modifying it.
- Never run repair, formatting, publication, dependency-installation, or arbitrary manifest commands.
- Use fixed, registered read-only probes. Git commands must be argument lists, not shell strings.
- Confine any optional reports or debug artifacts to explicitly declared owned paths.
- Prove through before/after filesystem snapshots that a no-write run changes nothing.
- Treat unreadable paths, non-Git inputs, missing history, and unsupported repository layouts as bounded degradation rather than invented evidence.

### Stable evidence

- Give every blocker, warning, and scope violation a deterministic finding ID.
- Derive identity from the capability version, finding kind, canonical repository-relative path, and stable subject fields—not timestamps, absolute machine paths, ordering, or prose.
- Return canonical paths, status, relevant hashes or Git identities, the rule that fired, and a concise remediation.
- Sort findings deterministically.
- Keep raw diffs temporary and explicit. Never copy diffs, source text, credentials, or filenames containing secrets into telemetry.

### Bounds and portability

- Enforce file-count, output-size, and execution-time budgets.
- Report omitted counts when evidence is truncated.
- Handle spaces, Unicode, path separators, case sensitivity, and repositories located outside an Agentic Workspace layout.
- Produce equivalent findings on Windows, Linux, and macOS for equivalent fixtures.
- Return the same result on repeated runs against unchanged state.

## Capability requirements

### `workspace.validate-scoped-delta`

The capability must compare either supplied snapshots or explicitly selected Git/filesystem states against a declared mutation allowlist.

It must:

- classify added, modified, deleted, renamed, and untracked artifacts;
- distinguish allowed changes from exact violations;
- identify generated artifacts without granting them permission merely because they are generated;
- handle overlapping allow and exclude patterns predictably;
- reject paths that escape the declared scope after canonicalization;
- detect writes outside owned report, cache, telemetry, and service-state paths;
- resolve only when every observed change is allowed;
- return the complete bounded violation set with stable IDs.

Required adversarial fixtures include traversal-like paths, case-only changes, symlink or junction boundaries where the platform supports them, rename pairs, ignored files, generated files outside owned paths, and an allowlist that is empty or overly broad.

### `workspace.change-packet`

The capability must produce an extractive packet that lets a host understand what changed without reading an unbounded diff.

It must include, when available:

- repository root, branch, HEAD, upstream, and dirty-worktree state;
- staged, unstaged, untracked, deleted, and renamed artifacts;
- base/head or before/after identities;
- artifact content hashes and bounded diff statistics;
- impacted repository relationships derived from registered graph inputs;
- relevant tests, validation commands, instructions, and documentation selected through fixed probes;
- omitted counts and degradation reasons.

Raw patch text is not part of the normal result or telemetry. If a caller explicitly requests a temporary diff artifact, its path, lifetime, and ownership must be declared.

Required fixtures include clean and dirty repositories, staged-plus-unstaged changes to the same file, binary files, renames, deletions, untracked files, detached HEAD, no commits, nested repositories, non-Git directories, and output-budget truncation.

### `repo.preflight`

The capability must identify blockers and the minimum safe validation set before a host changes or publishes a repository. It reports; it never repairs or publishes.

It must inspect, when available:

- canonical repository root, branch, HEAD, upstream, default branch, detached state, and worktree cleanliness;
- nested repositories, submodules, linked worktrees, and instruction-file scope;
- repository markers and declared validation commands from allowlisted configuration;
- generated or sensitive untracked artifacts, unexpectedly large files, unresolved merge state, and publication-target ambiguity;
- whether the current state is safe to inspect, change, commit, or publish as separate conclusions.

Recommended validations are data, not executable shell supplied by a manifest. Unknown project types must produce a review warning rather than a guessed command.

Required fixtures include clean and dirty branches, detached HEAD, ahead/behind/diverged upstream states, missing remotes, nested Git repositories, submodules, worktrees, merge or rebase state, repository paths with spaces, conflicting instruction files, and representative Python, Node, Rust, mixed, and unknown repositories.

## Fixture and review record

Create the Phase 1 dataset under a new versioned calibration directory rather than rewriting the `0.2.0` synthetic seeds. Each case must record:

- fixture ID and capability version;
- lane: `normal`, `ambiguous`, `degraded`, or `adversarial`;
- platform requirements;
- setup state and declared mutation allowlist;
- exact expected finding IDs, disposition, and degradation;
- expected changed-path and omitted counts;
- reviewer, review date, and rationale;
- before/after filesystem snapshot result.

Fixtures must be deterministic and self-contained. Tests may create temporary Git repositories, but must not depend on the developer's global Git configuration, network access, Foundry, model files, or workspace-relative paths.

## Gate and definition of done

Phase 1 passes only when all of the following are true:

1. Every fixture has human-reviewed expected results.
2. Every expected finding identity is reproduced exactly on repeated runs.
3. No unexpected finding is emitted in normal fixtures.
4. Every declared adversarial violation is detected.
5. Before/after snapshots show zero unauthorized mutations.
6. Non-Git and partially unreadable inputs degrade without fabricated Git evidence.
7. Output and candidate budgets truncate deterministically and report omitted counts.
8. Windows, Linux, and macOS CI pass the applicable fixture set on Python 3.10 and 3.13.
9. At least three real workspace tasks have been run in advisory mode and their false positives, missed hazards, and operator feedback are recorded.
10. A reviewer signs off the calibration record and changes the three capability states from `experimental` to `published`.

After the gate passes, publish the capabilities in the workspace cognition index, update only their consuming skills, repeat cold/no-write/idempotent audits, and release them as `0.3.0`. Retrieval and other model-backed calibration remains out of scope until then.

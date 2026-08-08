from __future__ import annotations

import subprocess
from pathlib import Path

from tiny_minds.integrations.workspace_memory import analysis, level1


def git(repo: Path, *args: str) -> None:
    completed = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if completed.returncode:
        raise AssertionError(completed.stderr)


def governed(updated: str, source: str) -> str:
    return f"""---
record_type: factual
status: current
confidence: high
updated: {updated}
last_updated: {updated}
sources:
  - {source}
---

# Record

This governed record has enough stable prose to participate in historical analysis and validation.
"""


def make_workspace(tmp_path: Path) -> Path:
    for domain in level1.DOMAINS:
        (tmp_path / domain).mkdir()
    (tmp_path / "README.md").write_text("# Workspace\n", encoding="utf-8")
    return tmp_path


def test_dirty_nested_git_source_uses_file_history(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    repo = workspace / "Projects" / "Nested"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "tiny@example.test")
    git(repo, "config", "user.name", "Tiny Tests")
    (repo / "source.txt").write_text("one", encoding="utf-8")
    (repo / "Record.md").write_text(governed("2020-01-01", "source.txt"), encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "baseline")
    (repo / "source.txt").write_text("dirty change", encoding="utf-8")
    documents = level1.collect_documents(workspace)
    findings = analysis.freshness_findings(documents, workspace)
    assert any(item.rule_id == "source-newer-than-verification" and "Projects/Nested/Record.md" in item.paths for item in findings)


def test_nested_git_cochange_jaccard_requires_three_shared_commits(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    repo = workspace / "Projects" / "Nested"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "tiny@example.test")
    git(repo, "config", "user.name", "Tiny Tests")
    for revision in range(3):
        (repo / "evidence.txt").write_text(str(revision), encoding="utf-8")
        (repo / "A.md").write_text(governed("2026-08-08", "evidence.txt") + f"\nA {revision}\n", encoding="utf-8")
        (repo / "B.md").write_text(governed("2026-08-08", "evidence.txt") + f"\nB {revision}\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", f"shared {revision}")
    documents = level1.collect_documents(workspace)
    pairs = analysis.cochange_pairs(documents, workspace)
    assert pairs[("Projects/Nested/A.md", "Projects/Nested/B.md")] == (1.0, 3)

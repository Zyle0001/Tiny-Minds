"""Deterministic Level 1 validator for the Markdown-first workspace.

Validation never edits source knowledge. Its only writes are the append-only event
log and the derived outstanding-findings report under Reports/Memory-Validation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote


SCHEMA_VERSION = 1
DOMAINS = ("Cognition", "Goals", "History", "Ideas", "Projects", "Skills")
EXCLUDED_DIRS = {
    ".git", ".agents", ".obsidian", ".opencode", ".venv", "venv",
    "tmp", "node_modules", "vendor", "dist", "build", "out", "target",
    "bin", "obj", ".svelte-kit", ".astro", ".next", "coverage",
    "__pycache__", "cache", "caches", "source", "sources",
}
RECORD_TYPES = {
    "factual", "architectural", "decision", "generative", "operational", "historical"
}
GOVERNED_TYPES = {"factual", "architectural", "decision"}
STATUSES = {"current", "provisional", "stale", "superseded", "archived"}
CONFIDENCES = {"high", "medium", "low"}
REQUIRED_FIELDS = ("record_type", "status", "confidence", "updated", "last_updated", "sources")
CANONICAL_INDEXES = {
    "README.md", "BOOTSTRAP.md", "Goals/Goals.md", "Projects/Projects.md",
    "Skills/Skills.md", "Ideas/Ideas.md",
}
PATH_EXTENSIONS = {
    ".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini",
    ".ps1", ".py", ".js", ".ts", ".mjs", ".cjs", ".svelte", ".astro",
    ".cs", ".cpp", ".c", ".h", ".hpp", ".csproj", ".sln", ".uplugin",
    ".uproject", ".build.cs", ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".svg", ".pdf", ".mp3", ".wav", ".tif", ".tiff",
}


@dataclass
class Document:
    path: Path
    relative: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    frontmatter_error: str | None = None

    @property
    def record_type(self) -> str | None:
        value = self.metadata.get("record_type")
        return value if isinstance(value, str) else None

    @property
    def governed(self) -> bool:
        return self.record_type in GOVERNED_TYPES


@dataclass
class Finding:
    rule_id: str
    severity: str
    fatal: bool
    message: str
    paths: list[str]
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def finding_id(self) -> str:
        discriminator = next(
            (self.evidence[key] for key in ("target", "source", "stable_id", "value", "cycle", "section_pair")
             if key in self.evidence),
            None,
        )
        identity = json.dumps(
            {"rule_id": self.rule_id, "paths": sorted(self.paths), "location": discriminator},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "fatal": self.fatal,
            "message": self.message,
            "paths": sorted(self.paths),
            "evidence": self.evidence,
        }


def canonical(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def content_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, PermissionError):
        return None


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        body = value[1:-1].strip()
        if not body:
            return []
        return [item.strip() for item in next(csv.reader([body], skipinitialspace=True))]
    if value in {"null", "Null", "NULL", "~"}:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str | None, int]:
    lines = text.splitlines()
    if not lines or lines[0].lstrip("\ufeff").strip() != "---":
        return {}, None, 0
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, "opening delimiter has no closing delimiter", len(lines)

    result: dict[str, Any] = {}
    current_list: str | None = None
    for line_number, line in enumerate(lines[1:end], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s+(.*?)\s*$", line)
        if item and current_list:
            result[current_list].append(parse_scalar(item.group(1)))
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$", line)
        if not match:
            return {}, f"unsupported or malformed frontmatter at line {line_number}", end + 1
        key, raw = match.group(1), match.group(2) or ""
        if key in result:
            return {}, f"duplicate frontmatter key '{key}' at line {line_number}", end + 1
        if raw.strip() == "":
            result[key] = []
            current_list = key
        else:
            result[key] = parse_scalar(raw)
            current_list = None
    return result, None, end + 1


def is_excluded(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    return any(part.lower() in EXCLUDED_DIRS for part in parts[:-1])


def collect_documents(root: Path) -> list[Document]:
    paths: list[Path] = list(root.glob("*.md"))
    for domain in DOMAINS:
        domain_path = root / domain
        if domain_path.is_dir():
            paths.extend(path for path in domain_path.rglob("*.md") if not is_excluded(path, root))
    documents: list[Document] = []
    for path in sorted(set(paths), key=lambda item: canonical(item, root).lower()):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        metadata, error, _ = parse_frontmatter(text)
        documents.append(Document(path, canonical(path, root), text, metadata, error))
    return documents


def project_root_for(path: Path, workspace: Path) -> Path | None:
    projects = (workspace / "Projects").resolve()
    try:
        relative = path.resolve().relative_to(projects)
    except ValueError:
        return None
    return projects / relative.parts[0] if relative.parts else None


def clean_target(value: str) -> str:
    target = value.strip()
    if target.startswith("<") and ">" in target:
        return target[1:target.index(">")]
    title = re.match(r"^(.*?)(?:\s+[\"'].*[\"'])$", target)
    return (title.group(1) if title else target).strip()


def metadata_target(value: str) -> tuple[str, bool]:
    target = value.strip()
    if target.startswith("[[") and target.endswith("]]" ):
        return target[2:-2].split("|", 1)[0].strip(), True
    markdown = re.fullmatch(r"\[[^\]]*\]\(([^)]+)\)", target)
    if markdown:
        return clean_target(markdown.group(1)), False
    return target, True


def extract_links(document: Document) -> list[tuple[str, str]]:
    _, _, body_start = parse_frontmatter(document.text)
    body = "\n".join(document.text.splitlines()[body_start:])
    body = re.sub(r"```.*?```|~~~.*?~~~", "", body, flags=re.DOTALL)
    body = re.sub(r"`[^`\n]*`", "", body)
    links: list[tuple[str, str]] = []
    for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", body):
        links.append(("markdown", clean_target(match.group(1))))
    for match in re.finditer(r"\[\[([^\]]+)\]\]", body):
        links.append(("wiki", match.group(1).split("|", 1)[0].strip()))
    return links


def without_fragment(target: str) -> str:
    return unquote(target.split("#", 1)[0].split("?", 1)[0]).strip()


def markdown_anchor(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[*`~]", "", value).strip().lower()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    # GitHub-style anchors replace each whitespace character; they do not
    # collapse the two spaces left when punctuation such as an em dash is removed.
    return re.sub(r"\s", "-", value)


def anchor_exists(path: Path, fragment: str) -> bool:
    if not fragment or path.suffix.lower() != ".md":
        return True
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return False
    wanted = unquote(fragment).strip().lower()
    for line in text.splitlines():
        explicit = re.search(r"\{#([^}]+)\}\s*$", line)
        if explicit and explicit.group(1).lower() == wanted:
            return True
        heading = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading and markdown_anchor(heading.group(1)) == wanted:
            return True
    return False


def is_external(target: str) -> bool:
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)) and not re.match(r"^[A-Za-z]:[\\/]", target)


@lru_cache(maxsize=None)
def wiki_candidates(workspace: str, stem: str) -> tuple[Path, ...]:
    root = Path(workspace)
    matches: list[Path] = []
    for domain in DOMAINS:
        domain_path = root / domain
        if not domain_path.is_dir():
            continue
        for current, directories, files in os.walk(domain_path):
            directories[:] = [name for name in directories if name.lower() not in EXCLUDED_DIRS]
            matches.extend(Path(current) / name for name in files
                           if name.lower().endswith(".md") and Path(name).stem.lower() == stem)
    matches.extend(path for path in root.glob("*.md") if path.stem.lower() == stem)
    return tuple(matches)


def candidate_paths(target: str, document: Document, root: Path, wiki: bool = False) -> list[Path]:
    target = without_fragment(target)
    if not target:
        return []
    path = Path(target.replace("/", os.sep))
    if path.is_absolute():
        bases = [path]
    else:
        bases = [document.path.parent / path]
        project_root = project_root_for(document.path, root)
        if project_root:
            bases.append(project_root / path)
        bases.append(root / path)
    candidates: list[Path] = []
    for base in bases:
        candidates.append(base)
        if not base.suffix:
            candidates.append(base.with_suffix(".md"))
            if wiki and base.parent.is_dir():
                candidates.extend(sorted(base.parent.glob(f"{base.name}.*")))
            candidates.append(base / f"{base.name}.md")
            candidates.append(base / "README.md")
    if wiki and len(path.parts) == 1:
        name = path.name.lower()
        candidates.extend(wiki_candidates(str(root.resolve()), name))
    return list(dict.fromkeys(candidates))


def resolve_target(target: str, document: Document, root: Path, wiki: bool = False) -> Path | None:
    if is_external(target):
        return None
    # Leading-slash links in project documentation are application routes, not
    # Windows filesystem paths (for example an Astro site's `/guides/` route).
    if target.startswith("/"):
        return None
    fragment = target.split("#", 1)[1].split("?", 1)[0] if "#" in target else ""
    if without_fragment(target) == "":
        return document.path.resolve() if anchor_exists(document.path, fragment) else Path("__MISSING__")
    for candidate in candidate_paths(target, document, root, wiki):
        if candidate.exists():
            resolved = candidate.resolve()
            return resolved if anchor_exists(resolved, fragment) else Path("__MISSING__")
    return Path("__MISSING__")


def looks_like_local_source(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or is_external(value.strip()):
        return False
    text = value.strip()
    if re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith(("./", "../", ".\\", "..\\")):
        return True
    if re.search(r"\s(?:in|at|from)\s+\.\.?[\\/]", text, flags=re.IGNORECASE):
        return False
    suffix = Path(text.rstrip("/\\")).suffix.lower()
    return "/" in text or "\\" in text or suffix in PATH_EXTENSIONS


def valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
    except ValueError:
        return False


def add_finding(findings: list[Finding], rule: str, severity: str, fatal: bool,
                message: str, paths: Iterable[str], **evidence: Any) -> None:
    findings.append(Finding(rule, severity, fatal, message, sorted(set(paths)), evidence))


def validate(root: Path) -> tuple[list[Document], list[Finding]]:
    documents = collect_documents(root)
    findings: list[Finding] = []
    incoming: dict[str, int] = {doc.relative: 0 for doc in documents}
    by_resolved = {doc.path.resolve(): doc.relative for doc in documents}
    ids: dict[str, list[str]] = {}
    supersedes_graph: dict[str, list[str]] = {}

    for doc in documents:
        if doc.path.name.upper().endswith("_TEMPLATE.MD"):
            continue
        fatal_context = doc.governed or doc.relative in CANONICAL_INDEXES
        if doc.frontmatter_error:
            add_finding(findings, "frontmatter-malformed", "error", fatal_context,
                        f"Malformed YAML frontmatter: {doc.frontmatter_error}", [doc.relative])
            continue

        record_type = doc.metadata.get("record_type")
        if record_type is not None and (not isinstance(record_type, str) or record_type not in RECORD_TYPES):
            add_finding(findings, "record-type-invalid", "error", True,
                        f"Invalid record_type: {record_type!r}", [doc.relative], value=record_type)
        if doc.governed:
            for key in REQUIRED_FIELDS:
                if key not in doc.metadata:
                    add_finding(findings, f"metadata-required-{key}", "error", True,
                                f"Governed record is missing required '{key}' metadata", [doc.relative])
            status = doc.metadata.get("status")
            if status is not None and status not in STATUSES:
                add_finding(findings, "status-invalid", "error", True,
                            f"Invalid governed-record status: {status!r}", [doc.relative], value=status)
            confidence = doc.metadata.get("confidence")
            if confidence is not None and confidence not in CONFIDENCES:
                add_finding(findings, "confidence-invalid", "error", True,
                            f"Invalid confidence: {confidence!r}", [doc.relative], value=confidence)
            for key in ("updated", "last_updated"):
                if key in doc.metadata and not valid_date(doc.metadata[key]):
                    add_finding(findings, f"date-invalid-{key}", "error", True,
                                f"'{key}' must be a real YYYY-MM-DD date", [doc.relative], value=doc.metadata[key])
            sources = doc.metadata.get("sources")
            if sources is not None and not isinstance(sources, list):
                add_finding(findings, "sources-not-list", "error", True,
                            "'sources' must be a YAML list", [doc.relative])
            elif isinstance(sources, list):
                if not sources:
                    add_finding(findings, "sources-empty", "warning", False,
                                "Governed record has an empty source list; confirm the note explains why", [doc.relative])
                for source in sources:
                    if not isinstance(source, str):
                        add_finding(findings, "source-item-invalid", "error", True,
                                    "Every source item must be a string", [doc.relative], value=source)
                        continue
                    if not looks_like_local_source(source):
                        continue
                    resolved = resolve_target(str(source), doc, root)
                    if resolved == Path("__MISSING__"):
                        add_finding(findings, "declared-source-missing", "error", True,
                                    f"Declared local source does not exist: {source}", [doc.relative], source=source)
                    elif resolved in by_resolved:
                        incoming[by_resolved[resolved]] += 1

        for key in ("id", "stable_id"):
            value = doc.metadata.get(key)
            if isinstance(value, str) and value.strip():
                ids.setdefault(value.strip(), []).append(doc.relative)
            elif value is not None:
                add_finding(findings, "stable-id-invalid", "error", True,
                            f"'{key}' must be a non-empty string", [doc.relative], value=value)

        for kind, target in extract_links(doc):
            if not target or is_external(target):
                continue
            resolved = resolve_target(target, doc, root, kind == "wiki")
            if resolved == Path("__MISSING__"):
                add_finding(findings, "internal-link-broken", "error" if fatal_context else "warning",
                            fatal_context, f"Internal {kind} link does not resolve: {target}",
                            [doc.relative], target=target, link_kind=kind)
            elif resolved in by_resolved:
                incoming[by_resolved[resolved]] += 1

        supersedes = doc.metadata.get("supersedes")
        if supersedes is not None and not isinstance(supersedes, list):
            add_finding(findings, "supersedes-not-list", "error", doc.governed,
                        "'supersedes' must be a YAML list", [doc.relative])
        elif isinstance(supersedes, list):
            resolved_targets: list[str] = []
            for target in supersedes:
                if not isinstance(target, str):
                    add_finding(findings, "supersedes-item-invalid", "error", doc.governed,
                                "Every supersedes item must be a path string", [doc.relative], value=target)
                    continue
                normalized, wiki = metadata_target(target)
                resolved = resolve_target(normalized, doc, root, wiki=wiki)
                if resolved == Path("__MISSING__"):
                    add_finding(findings, "supersedes-target-missing", "error", doc.governed,
                                f"Superseded record does not exist: {target}", [doc.relative], target=target)
                elif resolved in by_resolved:
                    resolved_targets.append(by_resolved[resolved])
                    incoming[by_resolved[resolved]] += 1
            supersedes_graph[doc.relative] = resolved_targets

        related = doc.metadata.get("related")
        if related is not None and not isinstance(related, list):
            add_finding(findings, "related-not-list", "error", doc.governed,
                        "'related' must be a YAML list", [doc.relative])
        elif isinstance(related, list):
            for target in related:
                if not isinstance(target, str):
                    add_finding(findings, "related-item-invalid", "error", doc.governed,
                                "Every related item must be a path string", [doc.relative], value=target)
                    continue
                normalized, wiki = metadata_target(target)
                resolved = resolve_target(normalized, doc, root, wiki=wiki)
                if resolved == Path("__MISSING__"):
                    add_finding(findings, "related-target-missing", "error", doc.governed,
                                f"Related record does not exist: {target}", [doc.relative], target=target)
                elif resolved in by_resolved:
                    incoming[by_resolved[resolved]] += 1

    for stable_id, paths in ids.items():
        if len(paths) > 1:
            add_finding(findings, "stable-id-duplicate", "error", True,
                        f"Stable ID is declared by {len(paths)} documents: {stable_id}", paths, stable_id=stable_id)

    seen_cycles: set[tuple[str, ...]] = set()
    def walk(node: str, trail: list[str]) -> None:
        if node in trail:
            cycle = trail[trail.index(node):] + [node]
            key = tuple(sorted(set(cycle)))
            if key not in seen_cycles:
                seen_cycles.add(key)
                add_finding(findings, "supersedes-cycle", "error", True,
                            "Supersession relationship contains a cycle", cycle, cycle=cycle)
            return
        for target in supersedes_graph.get(node, []):
            walk(target, trail + [node])
    for node in supersedes_graph:
        walk(node, [])

    conventional_names = {"PROJECT.md", "README.md", "TASKS.md", "DECISIONS.md", "AGENTS.md", "SOURCES.md"}
    for doc in documents:
        if doc.path.name.upper().endswith("_TEMPLATE.MD"):
            continue
        if doc.governed and incoming[doc.relative] == 0 and doc.path.name not in conventional_names:
            add_finding(findings, "governed-record-orphan", "warning", False,
                        "Governed record has no incoming Markdown or wikilinks", [doc.relative])

    findings.sort(key=lambda item: (not item.fatal, item.rule_id, item.paths, item.message))
    return documents, findings


def run_git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                                text=True, check=False, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def repository_root(path: Path, workspace: Path) -> Path | None:
    current = path if path.is_dir() else path.parent
    workspace = workspace.resolve()
    while True:
        if (current / ".git").exists():
            return current
        if current.resolve() == workspace or current.parent == current:
            return None
        current = current.parent


def verification_for_paths(paths: list[str], workspace: Path) -> list[dict[str, Any]]:
    baselines: dict[str, dict[str, Any]] = {}
    for relative in paths:
        path = Path(relative)
        if not path.is_absolute():
            path = workspace / relative
        repo = repository_root(path, workspace)
        if repo:
            key = canonical(repo, workspace)
            if key not in baselines:
                head = run_git(["rev-parse", "HEAD"], repo)
                status = run_git(["status", "--porcelain"], repo)
                baselines[key] = {
                    "repository": key, "verified_at_commit": head,
                    "worktree": "dirty" if status else "clean",
                }
        else:
            key = canonical(path, workspace)
            if key not in baselines:
                try:
                    modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
                except OSError:
                    modified = None
                baselines[key] = {
                    "repository": None, "path": key, "verified_at_commit": None,
                    "worktree": "not-versioned", "content_sha256": content_hash(path),
                    "modified_at": modified,
                }
    return [baselines[key] for key in sorted(baselines)]


def observation_hash(finding: Finding, verification: list[dict[str, Any]]) -> str:
    payload = {"finding": finding.as_dict(), "verification": verification}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSONL event at {path}:{line_number}: {exc}") from exc
    return events


def unresolved_events(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    unresolved: dict[str, dict[str, Any]] = {}
    for event in events:
        finding_id = event.get("finding_id")
        if not finding_id:
            continue
        if event.get("event_type") == "finding":
            unresolved[finding_id] = event
        elif event.get("event_type") == "resolution":
            unresolved.pop(finding_id, None)
    return unresolved


def append_findings(findings: list[Finding], workspace: Path, events_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    existing = load_events(events_path)
    unresolved = unresolved_events(existing)
    now = datetime.now(timezone.utc).isoformat()
    appended: list[dict[str, Any]] = []
    for finding in findings:
        verification = verification_for_paths(finding.paths, workspace)
        observed_hash = observation_hash(finding, verification)
        previous = unresolved.get(finding.finding_id)
        if previous and previous.get("observation_hash") == observed_hash:
            continue
        event_id_source = f"finding:{finding.finding_id}:{observed_hash}:{now}"
        event = {
            "schema_version": SCHEMA_VERSION,
            "event_type": "finding",
            "event_id": hashlib.sha256(event_id_source.encode("utf-8")).hexdigest()[:24],
            **finding.as_dict(),
            "observed_at": now,
            "observation_hash": observed_hash,
            "verification": verification,
        }
        appended.append(event)
        unresolved[finding.finding_id] = event
    if appended:
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("a", encoding="utf-8", newline="\n") as stream:
            for event in appended:
                stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
    return appended, list(unresolved.values())


def write_outstanding(path: Path, unresolved: list[dict[str, Any]], current_ids: set[str]) -> None:
    fatal_count = sum(bool(item.get("fatal")) for item in unresolved)
    warning_count = len(unresolved) - fatal_count
    lines = [
        "# Outstanding Memory-Validation Findings", "",
        "This file is derived from `events.jsonl`. Validation does not repair workspace knowledge.", "",
        f"- Unresolved: {len(unresolved)}",
        f"- Structural failures: {fatal_count}",
        f"- Advisories: {warning_count}", "",
    ]
    for item in sorted(unresolved, key=lambda value: (not value.get("fatal", False), value.get("rule_id", ""), value.get("paths", []))):
        present = item.get("finding_id") in current_ids
        marker = "error" if item.get("fatal") else "advisory"
        lines.extend([
            f"## {item.get('rule_id')} — {marker}", "",
            f"- Finding ID: `{item.get('finding_id')}`",
            f"- Observed in latest run: {'yes' if present else 'no'}",
            f"- Paths: {', '.join(f'`{value}`' for value in item.get('paths', []))}",
            f"- Message: {item.get('message', '')}", "",
        ])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[5])
    parser.add_argument("--no-write", action="store_true", help="Scan without writing validator-owned reports")
    parser.add_argument("--json", action="store_true", help="Write the current-run result as JSON to stdout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = args.workspace.resolve()
    documents, findings = validate(workspace)
    fatal_count = sum(item.fatal for item in findings)
    appended: list[dict[str, Any]] = []
    unresolved_count: int | None = None
    if not args.no_write:
        report_root = workspace / "Reports" / "Memory-Validation"
        appended, unresolved = append_findings(findings, workspace, report_root / "events.jsonl")
        write_outstanding(report_root / "Outstanding.md", unresolved, {item.finding_id for item in findings})
        unresolved_count = len(unresolved)

    result = {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(workspace),
        "documents_scanned": len(documents),
        "findings": [item.as_dict() for item in findings],
        "fatal_count": fatal_count,
        "advisory_count": len(findings) - fatal_count,
        "events_appended": len(appended),
        "unresolved_count": unresolved_count,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Scanned {len(documents)} Markdown documents.")
        print(f"Current findings: {fatal_count} structural failure(s), {len(findings) - fatal_count} advisory finding(s).")
        if not args.no_write:
            print(f"Appended {len(appended)} new observation event(s); {unresolved_count} finding(s) remain unresolved.")
        for finding in findings:
            level = "ERROR" if finding.fatal else "WARN"
            print(f"[{level}] {finding.rule_id} {', '.join(finding.paths)}: {finding.message}")
    return 1 if fatal_count else 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tiny_minds" / "integrations" / "workspace_memory" / "level1.py"
SPEC = importlib.util.spec_from_file_location("memory_validator", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


class MemoryValidatorTests(unittest.TestCase):
    def make_workspace(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        for name in validator.DOMAINS:
            (root / name).mkdir()
        (root / "README.md").write_text("# Workspace\n", encoding="utf-8")
        return temporary, root

    def governed(self, sources: str = "  - evidence.txt", extra: str = "") -> str:
        return f"""---
record_type: factual
status: current
confidence: high
updated: 2026-08-08
last_updated: 2026-08-08
sources:
{sources}
{extra}---

# Record
"""

    def test_valid_governed_record_and_relative_source(self) -> None:
        temporary, root = self.make_workspace()
        self.addCleanup(temporary.cleanup)
        project = root / "Projects" / "Example"
        project.mkdir()
        (project / "evidence.txt").write_text("evidence", encoding="utf-8")
        (project / "PROJECT.md").write_text(self.governed(), encoding="utf-8")
        _, findings = validator.validate(root)
        self.assertEqual([], [item for item in findings if item.fatal])

    def test_required_metadata_and_missing_source_are_fatal(self) -> None:
        temporary, root = self.make_workspace()
        self.addCleanup(temporary.cleanup)
        note = root / "Projects" / "Broken.md"
        note.write_text("---\nrecord_type: factual\nstatus: current\nsources:\n  - absent.txt\n---\n", encoding="utf-8")
        _, findings = validator.validate(root)
        rules = {item.rule_id for item in findings if item.fatal}
        self.assertTrue({"metadata-required-confidence", "metadata-required-updated", "metadata-required-last_updated", "declared-source-missing"} <= rules)

    def test_broken_link_is_fatal_only_for_governed_or_index_notes(self) -> None:
        temporary, root = self.make_workspace()
        self.addCleanup(temporary.cleanup)
        (root / "README.md").write_text("[missing](missing.md)\n", encoding="utf-8")
        (root / "Ideas" / "draft.md").write_text("[also missing](other.md)\n", encoding="utf-8")
        _, findings = validator.validate(root)
        by_path = {item.paths[0]: item for item in findings if item.rule_id == "internal-link-broken"}
        self.assertTrue(by_path["README.md"].fatal)
        self.assertFalse(by_path["Ideas/draft.md"].fatal)

    def test_fragment_only_link_checks_heading_anchor(self) -> None:
        temporary, root = self.make_workspace()
        self.addCleanup(temporary.cleanup)
        note = root / "Ideas" / "anchors.md"
        note.write_text("# Note\n\n[good](#a-real-heading) [bad](#absent)\n\n## A Real Heading\n", encoding="utf-8")
        _, findings = validator.validate(root)
        broken = [item for item in findings if item.rule_id == "internal-link-broken"]
        self.assertEqual(1, len(broken))
        self.assertEqual("#absent", broken[0].evidence["target"])

    def test_wikilink_resolution_and_backlink_prevent_orphan_warning(self) -> None:
        temporary, root = self.make_workspace()
        self.addCleanup(temporary.cleanup)
        project = root / "Projects" / "Example"
        project.mkdir()
        (project / "evidence.txt").write_text("evidence", encoding="utf-8")
        (project / "Architecture.md").write_text(self.governed(), encoding="utf-8")
        (project / "README.md").write_text("See [[Architecture]].\n", encoding="utf-8")
        _, findings = validator.validate(root)
        orphan_paths = {item.paths[0] for item in findings if item.rule_id == "governed-record-orphan"}
        self.assertNotIn("Projects/Example/Architecture.md", orphan_paths)

    def test_attachment_wikilink_and_project_root_relative_path_resolve(self) -> None:
        temporary, root = self.make_workspace()
        self.addCleanup(temporary.cleanup)
        project = root / "Projects" / "Example"
        nested = project / "Architecture"
        nested.mkdir(parents=True)
        (project / "SOURCE_MANIFEST.json").write_text("{}", encoding="utf-8")
        (project / "evidence.txt").write_text("evidence", encoding="utf-8")
        note = self.governed().replace("# Record", "# Record\n\n[[SOURCE_MANIFEST]]\n\n[Evidence](evidence.txt)")
        (nested / "Record.md").write_text(note, encoding="utf-8")
        _, findings = validator.validate(root)
        broken = [item for item in findings if item.rule_id == "internal-link-broken"]
        self.assertEqual([], broken)

    def test_templates_allow_date_placeholders(self) -> None:
        temporary, root = self.make_workspace()
        self.addCleanup(temporary.cleanup)
        template = self.governed(sources="  []").replace("2026-08-08", "YYYY-MM-DD")
        (root / "Projects" / "PROJECT_TEMPLATE.md").write_text(template, encoding="utf-8")
        _, findings = validator.validate(root)
        self.assertEqual([], [item for item in findings if "TEMPLATE" in item.paths[0]])

    def test_inline_lists_and_related_relationship_are_supported(self) -> None:
        temporary, root = self.make_workspace()
        self.addCleanup(temporary.cleanup)
        project = root / "Projects" / "Example"
        project.mkdir()
        (project / "evidence.txt").write_text("evidence", encoding="utf-8")
        target = self.governed()
        source = self.governed().replace("sources:\n  - evidence.txt", "sources: [evidence.txt]").replace(
            "---\n\n# Record", 'related: ["[[Target|Target note]]"]\n---\n\n# Record'
        )
        (project / "Target.md").write_text(target, encoding="utf-8")
        (project / "Source.md").write_text(source, encoding="utf-8")
        _, findings = validator.validate(root)
        self.assertEqual([], [item for item in findings if item.fatal])
        orphan_paths = {item.paths[0] for item in findings if item.rule_id == "governed-record-orphan"}
        self.assertNotIn("Projects/Example/Target.md", orphan_paths)

    def test_duplicate_stable_id_and_supersedes_cycle_are_fatal(self) -> None:
        temporary, root = self.make_workspace()
        self.addCleanup(temporary.cleanup)
        project = root / "Projects" / "Example"
        project.mkdir()
        (project / "evidence.txt").write_text("evidence", encoding="utf-8")
        a = self.governed(extra="stable_id: same\nsupersedes:\n  - B.md\n")
        b = self.governed(extra="stable_id: same\nsupersedes:\n  - A.md\n")
        (project / "A.md").write_text(a, encoding="utf-8")
        (project / "B.md").write_text(b, encoding="utf-8")
        _, findings = validator.validate(root)
        rules = {item.rule_id for item in findings if item.fatal}
        self.assertIn("stable-id-duplicate", rules)
        self.assertIn("supersedes-cycle", rules)

    def test_event_log_deduplicates_unchanged_observation(self) -> None:
        temporary, root = self.make_workspace()
        self.addCleanup(temporary.cleanup)
        finding = validator.Finding("test-rule", "warning", False, "message", ["README.md"])
        path = root / "Reports" / "Memory-Validation" / "events.jsonl"
        first, _ = validator.append_findings([finding], root, path)
        second, unresolved = validator.append_findings([finding], root, path)
        self.assertEqual(1, len(first))
        self.assertEqual(0, len(second))
        self.assertEqual(1, len(unresolved))
        self.assertEqual(1, len(path.read_text(encoding="utf-8").splitlines()))

    def test_finding_id_is_stable_across_message_changes(self) -> None:
        first = validator.Finding("rule", "warning", False, "one", ["b.md", "a.md"])
        second = validator.Finding("rule", "error", True, "two", ["a.md", "b.md"])
        self.assertEqual(first.finding_id, second.finding_id)

    def test_different_missing_targets_have_distinct_finding_ids(self) -> None:
        first = validator.Finding("internal-link-broken", "error", True, "missing", ["note.md"], {"target": "a.md"})
        second = validator.Finding("internal-link-broken", "error", True, "missing", ["note.md"], {"target": "b.md"})
        self.assertNotEqual(first.finding_id, second.finding_id)


if __name__ == "__main__":
    unittest.main()

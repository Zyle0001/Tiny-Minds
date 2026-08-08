from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tiny_minds.cli", *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def test_capabilities_stdout_is_one_json_document() -> None:
    completed = run_cli("capabilities", "--json")
    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert payload["schema_version"] == 1
    assert payload["runtime"] == "tiny-minds-core"
    assert payload["capabilities"] == ["core.hash.sha256", "core.structure.validate-mapping"]


def test_workspace_capabilities_require_explicit_integration() -> None:
    completed = run_cli("capabilities", "--integration", "workspace-memory", "--json")
    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert "workspace.memory.structural" in payload["capabilities"]


def test_core_doctor_has_no_workspace_or_provider_requirement(tmp_path: Path) -> None:
    isolated_env = {
        key: value for key, value in os.environ.items()
        if "FOUNDRY" not in key.upper()
        and "AGENTIC" not in key.upper()
        and not key.upper().startswith("TINY_MINDS")
        and key.upper() not in {"PYTHONPATH", "VIRTUAL_ENV"}
    }
    isolated_env["PATH"] = str(Path(sys.executable).parent)
    completed = subprocess.run(
        [sys.executable, "-m", "tiny_minds.cli", "doctor", "--json"],
        cwd=tmp_path, capture_output=True, text=True, check=False, timeout=20,
        env=isolated_env,
    )
    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["status"] == "healthy"
    assert payload["providers"] == []
    assert payload["integrations"] == {}


def test_invalid_pipeline_has_contract_exit_code(tmp_path: Path) -> None:
    completed = run_cli("run", "missing", "--workspace", str(tmp_path), "--json")
    payload = json.loads(completed.stdout)
    assert completed.returncode == 3
    assert payload["error_type"] == "invalid-request"


def test_input_schema_version_is_rejected(tmp_path: Path) -> None:
    pipeline_dir = tmp_path / "Cognition" / "pipelines"
    pipeline_dir.mkdir(parents=True)
    (pipeline_dir / "empty.yaml").write_text(
        "schema_version: 1\nid: empty\nversion: '1'\nnodes: []\n", encoding="utf-8"
    )
    request = tmp_path / "request.json"
    request.write_text('{"schema_version":2}', encoding="utf-8")
    completed = run_cli("run", "empty", "--workspace", str(tmp_path), "--input", str(request), "--json")
    assert completed.returncode == 3
    assert json.loads(completed.stdout)["error_type"] == "invalid-request"

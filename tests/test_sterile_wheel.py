from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


RUN_STERILE = os.environ.get("TINY_MINDS_RUN_STERILE_WHEEL") == "1"


def run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=timeout
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Command failed ({completed.returncode}): {command}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


@pytest.mark.sterile
@pytest.mark.skipif(not RUN_STERILE, reason="set TINY_MINDS_RUN_STERILE_WHEEL=1 for isolated wheel acceptance")
def test_base_wheel_functions_without_workspace_or_foundry(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    source = tmp_path / "source"
    shutil.copytree(
        repo,
        source,
        ignore=shutil.ignore_patterns(".git", ".venv", ".pytest_cache", "__pycache__", "*.egg-info", "build"),
    )
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    build_env = dict(os.environ)
    run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheelhouse), str(source)],
        cwd=tmp_path,
        env=build_env,
    )
    wheels = list(wheelhouse.glob("tiny_minds-*.whl"))
    assert len(wheels) == 1

    sterile = tmp_path / "sterile"
    sterile.mkdir()
    venv = sterile / "venv"
    run([sys.executable, "-m", "venv", str(venv)], cwd=sterile, env=build_env)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    executable = venv / ("Scripts/tiny-minds.exe" if os.name == "nt" else "bin/tiny-minds")
    run([str(python), "-m", "pip", "install", str(wheels[0])], cwd=sterile, env=build_env)

    sterile_env = {
        key: value for key, value in os.environ.items()
        if "FOUNDRY" not in key.upper()
        and "AGENTIC" not in key.upper()
        and not key.upper().startswith("TINY_MINDS")
        and key.upper() not in {"PYTHONPATH", "VIRTUAL_ENV"}
    }
    sterile_env["PATH"] = str(python.parent)
    forbidden = {"Tools", "Cognition", "Projects", "Metrics", "Reports", "foundry-local-runtime"}
    assert forbidden.isdisjoint({item.name for item in sterile.iterdir()})

    probe = run(
        [str(python), "-c", (
            "import importlib.util,json;"
            "print(json.dumps({'psutil':importlib.util.find_spec('psutil') is not None,"
            "'numpy':importlib.util.find_spec('numpy') is not None}))"
        )],
        cwd=sterile,
        env=sterile_env,
    )
    installed = json.loads(probe.stdout)
    assert installed == {"psutil": False, "numpy": False}

    doctor = run([str(executable), "doctor", "--json"], cwd=sterile, env=sterile_env)
    doctor_payload = json.loads(doctor.stdout)
    assert doctor_payload["status"] == "healthy"
    assert doctor_payload["providers"] == []
    assert doctor_payload["integrations"] == {}

    capabilities = run([str(executable), "capabilities", "--json"], cwd=sterile, env=sterile_env)
    assert json.loads(capabilities.stdout)["capabilities"] == [
        "core.hash.sha256", "core.provider.invoke", "core.structure.validate-mapping"
    ]

    manifest = sterile / "portable.yaml"
    manifest.write_text(
        """schema_version: 1
id: sterile-portable
version: '1'
nodes:
  - id: hash
    capability: core.hash.sha256
    config: {input_key: value}
  - id: structure
    capability: core.structure.validate-mapping
    config: {input_key: document, required: [id, kind]}
  - id: provider
    capability: core.provider.invoke
    required: false
    config: {provider: embeddings, operation: embed}
""",
        encoding="utf-8",
    )
    request = sterile / "input.json"
    request.write_text('{"value":"sterile","document":{"id":1,"kind":"proof"}}', encoding="utf-8")
    pipeline = subprocess.run(
        [str(executable), "run", str(manifest), "--input", str(request), "--no-write", "--json"],
        cwd=sterile, env=sterile_env, capture_output=True, text=True, check=False, timeout=30,
    )
    assert pipeline.returncode == 2
    result = json.loads(pipeline.stdout)
    assert result["status"] == "partial"
    assert result["primitives"]["hash"]["status"] == "success"
    assert result["primitives"]["structure"]["data"]["valid"] is True
    assert result["primitives"]["provider"]["status"] == "unavailable"
    assert "not configured" in result["primitives"]["provider"]["diagnostics"][0]
    assert forbidden.isdisjoint({item.name for item in sterile.iterdir()})

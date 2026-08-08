from __future__ import annotations

import json
import os
import runpy
import shutil
import subprocess
import sys
import threading
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
        "core.hash.sha256", "core.structure.validate-mapping"
    ]

    manifest = sterile / "portable.yaml"
    manifest.write_text(
        """schema_version: 1
id: sterile-portable
version: '1'
integrations: [generic-workspace]
nodes:
  - id: hash
    capability: core.hash.sha256
    config: {input_key: value}
  - id: structure
    capability: core.structure.validate-mapping
    config: {input_key: document, required: [id, kind]}
  - id: retrieve
    capability: workspace.retrieve-context
""",
        encoding="utf-8",
    )
    request = sterile / "input.json"
    request.write_text('{"value":"sterile","document":{"id":1,"kind":"proof"},"query":"sterile","documents":[{"path":"proof.md","text":"sterile proof"}]}', encoding="utf-8")
    pipeline = subprocess.run(
        [str(executable), "run", str(manifest), "--input", str(request), "--no-write", "--json"],
        cwd=sterile, env=sterile_env, capture_output=True, text=True, check=False, timeout=30,
    )
    assert pipeline.returncode == 2
    result = json.loads(pipeline.stdout)
    assert result["status"] == "partial"
    assert result["primitives"]["hash"]["status"] == "success"
    assert result["primitives"]["structure"]["data"]["valid"] is True
    assert result["primitives"]["retrieve"]["status"] == "degraded"
    assert "provider unavailable" in result["primitives"]["retrieve"]["diagnostics"][0].lower()
    assert forbidden.isdisjoint({item.name for item in sterile.iterdir()})


@pytest.mark.sterile
@pytest.mark.skipif(not RUN_STERILE, reason="set TINY_MINDS_RUN_STERILE_WHEEL=1 for isolated wheel acceptance")
def test_separate_http_provider_extension_without_foundry(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    env = dict(os.environ)
    run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheelhouse), str(repo)], cwd=tmp_path, env=env)
    run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheelhouse), str(repo / "examples" / "http-provider")], cwd=tmp_path, env=env)
    sterile = tmp_path / "sterile"
    sterile.mkdir()
    venv = sterile / "venv"
    run([sys.executable, "-m", "venv", str(venv)], cwd=sterile, env=env)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    executable = venv / ("Scripts/tiny-minds.exe" if os.name == "nt" else "bin/tiny-minds")
    core_wheel = next(wheelhouse.glob("tiny_minds-*.whl"))
    provider_wheel = next(wheelhouse.glob("tiny_minds_example_http_provider-*.whl"))
    run([str(python), "-m", "pip", "install", str(core_wheel)], cwd=sterile, env=env)
    run([str(python), "-m", "pip", "install", "--no-deps", str(provider_wheel)], cwd=sterile, env=env)
    sterile_env = {key: value for key, value in env.items() if "FOUNDRY" not in key.upper() and "AGENTIC" not in key.upper() and not key.upper().startswith("TINY_MINDS")}
    host_module = runpy.run_path(
        str(repo / "examples" / "http-provider" / "tiny_minds_example_http" / "fake_server.py")
    )
    server = host_module["ThreadingHTTPServer"](("127.0.0.1", 0), host_module["Handler"])
    port = server.server_address[1]
    host_thread = threading.Thread(target=server.serve_forever, name="tiny-minds-fake-http", daemon=True)
    host_thread.start()
    try:
        config = sterile / "config.yaml"
        config.write_text(f"""schema_version: 1
providers:
  - {{id: embeddings, kind: embeddings, implementation: example-http, endpoint: 'http://127.0.0.1:{port}', timeout_seconds: 5}}
  - {{id: reranker, kind: reranker, implementation: example-http, endpoint: 'http://127.0.0.1:{port}', timeout_seconds: 5}}
  - {{id: nli, kind: nli, implementation: example-http, endpoint: 'http://127.0.0.1:{port}', timeout_seconds: 5}}
  - {{id: classification, kind: classification, implementation: example-http, endpoint: 'http://127.0.0.1:{port}', timeout_seconds: 5}}
""", encoding="utf-8")
        manifest = sterile / "retrieve.yaml"
        manifest.write_text("""schema_version: 1
id: external-provider
version: '1'
integrations: [generic-workspace]
nodes:
  - {id: retrieve, capability: workspace.retrieve-context}
""", encoding="utf-8")
        request = sterile / "input.json"
        request.write_text('{"query":"alpha","documents":[{"path":"a","text":"alpha memory"},{"path":"b","text":"beta music"}]}', encoding="utf-8")
        completed = subprocess.run(
            [str(executable), "run", str(manifest), "--config", str(config), "--input", str(request), "--no-write", "--json"],
            cwd=sterile, env=sterile_env, capture_output=True, text=True, check=False, timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout)
        assert payload["primitives"]["retrieve"]["data"]["results"][0]["path"] == "a"
        probe_code = (
            "from pathlib import Path;from tiny_minds.application import build_configured_providers;"
            "from tiny_minds.providers import *;c=load_runtime_config(Path(r'" + str(config) + "'));"
            "p=build_configured_providers(c);"
            "assert p.get('nli').nli(NliRequest(pairs=[NliPair(premise='alpha',hypothesis='alpha')])).scores;"
            "assert p.get('classification').classify(ClassificationRequest(texts=['alpha'],labels=['alpha','beta'])).scores"
        )
        run([str(python), "-c", probe_code], cwd=sterile, env=sterile_env)
        assert not (sterile / "Tools").exists()
        assert "FOUNDRY" not in " ".join(sterile_env).upper()
    finally:
        server.shutdown()
        server.server_close()
        host_thread.join(timeout=5)
        assert not host_thread.is_alive()

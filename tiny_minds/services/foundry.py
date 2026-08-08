from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import psutil


class FoundryServiceError(RuntimeError):
    pass


def _json_request(url: str, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 3.0) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FoundryServiceError(f"Foundry returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise FoundryServiceError(f"Cannot reach Foundry at {url}: {exc}") from exc


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


class FoundryManager:
    def __init__(self, workspace: Path, record_telemetry: bool = False) -> None:
        self.workspace = workspace.resolve()
        self.record_telemetry = record_telemetry
        self.state_root = self.workspace / "tmp" / "tiny-minds" / "services"
        self.state_path = self.state_root / "foundry.json"

    def _record(self, action: str, payload: dict[str, Any]) -> None:
        if not self.record_telemetry:
            return
        try:
            from ..telemetry import append_service_telemetry
            append_service_telemetry(self.workspace, action, payload)
        except OSError:
            pass

    @staticmethod
    def _healthy(base_url: str) -> bool:
        try:
            payload = _json_request(f"{base_url}/status", timeout=0.75)
            return isinstance(payload, dict)
        except FoundryServiceError:
            return False

    def _read_state(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _command_fingerprint(command: list[str]) -> str:
        normalized = json.dumps([str(item).replace("\\", "/") for item in command], separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _process_matches(state: dict[str, Any]) -> bool:
        if not state.get("managed"):
            return False
        try:
            process = psutil.Process(int(state["pid"]))
            command = process.cmdline()
            return process.is_running() and FoundryManager._command_fingerprint(command) == state.get("command_fingerprint")
        except (psutil.Error, KeyError, ValueError):
            return False

    def status(self, preferred_port: int = 8123) -> dict[str, Any]:
        state = self._read_state()
        if state:
            base_url = str(state.get("base_url", ""))
            healthy = bool(base_url) and self._healthy(base_url)
            return {**state, "healthy": healthy, "process_matches": self._process_matches(state)}
        base_url = f"http://127.0.0.1:{preferred_port}"
        return {"service": "foundry", "managed": False, "base_url": base_url, "healthy": self._healthy(base_url)}

    def ensure(self, preferred_port: int = 8123, timeout_seconds: float = 25.0) -> dict[str, Any]:
        current = self.status(preferred_port)
        if current.get("healthy"):
            self._record("reuse", current)
            return current

        repo = self.workspace / "Tools" / "foundry-local-runtime"
        python_candidates = [
            repo / "ONNX host service" / "env" / "Scripts" / "python.exe",
            repo / ".venv" / "Scripts" / "python.exe",
            repo / ".venv" / "bin" / "python",
        ]
        python = next((path for path in python_candidates if path.exists()), None)
        if python is None:
            raise FoundryServiceError(
                "Foundry Python environment is not installed; set up Tools/foundry-local-runtime first"
            )

        port = preferred_port
        while not _port_available(port):
            candidate_url = f"http://127.0.0.1:{port}"
            if self._healthy(candidate_url):
                reused = {"service": "foundry", "managed": False, "port": port, "base_url": candidate_url, "healthy": True}
                self._record("reuse", reused)
                return reused
            port += 1
            if port > preferred_port + 50:
                raise FoundryServiceError("No available loopback port found for Foundry")

        self.state_root.mkdir(parents=True, exist_ok=True)
        log_path = self.state_root / "foundry.log"
        command = [str(python), "-m", "uvicorn", "onnx_host.main:app", "--host", "127.0.0.1", "--port", str(port)]
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                command,
                cwd=repo,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
        base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise FoundryServiceError(f"Foundry exited during startup; inspect {log_path}")
            if self._healthy(base_url):
                break
            time.sleep(0.2)
        else:
            process.terminate()
            raise FoundryServiceError(f"Foundry did not become healthy within {timeout_seconds}s")

        state = {
            "service": "foundry",
            "managed": True,
            "pid": process.pid,
            "port": port,
            "base_url": base_url,
            "started_at": time.time(),
            "command_fingerprint": self._command_fingerprint(command),
            "command": command,
            "log_path": str(log_path),
        }
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)
        started = {**state, "healthy": True, "process_matches": True}
        self._record("start", started)
        return started

    def stop(self) -> dict[str, Any]:
        state = self._read_state()
        if not state:
            return {"service": "foundry", "status": "not_managed"}
        if not self._process_matches(state):
            raise FoundryServiceError("Refusing to stop Foundry because the recorded PID or command does not match")
        process = psutil.Process(int(state["pid"]))
        process.terminate()
        try:
            process.wait(timeout=10)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        self.state_path.unlink(missing_ok=True)
        stopped = {"service": "foundry", "status": "stopped", "pid": state["pid"], "port": state.get("port")}
        self._record("stop", stopped)
        return stopped

    def ensure_model(self, model_id: str, preferred_port: int = 8123) -> dict[str, Any]:
        service = self.ensure(preferred_port)
        base_url = str(service["base_url"])
        try:
            model = _json_request(f"{base_url}/v1/models/{model_id}")
        except FoundryServiceError as exc:
            raise FoundryServiceError(
                f"Model '{model_id}' is not installed in Foundry; run its explicit installer first"
            ) from exc
        if not model.get("loaded"):
            _json_request(f"{base_url}/models/load", method="POST", payload={"id": model_id}, timeout=60.0)
        return {**service, "model_id": model_id, "model_loaded": True}

    def embed(self, texts: list[str], model_id: str, preferred_port: int = 8123) -> tuple[list[list[float]], dict[str, Any]]:
        service = self.ensure_model(model_id, preferred_port)
        payload = _json_request(
            f"{service['base_url']}/v1/embeddings",
            method="POST",
            payload={"model": model_id, "input": texts},
            timeout=120.0,
        )
        vectors = [item["embedding"] for item in sorted(payload.get("data", []), key=lambda item: item["index"])]
        if len(vectors) != len(texts):
            raise FoundryServiceError("Foundry returned a different number of embeddings than requested")
        return vectors, service

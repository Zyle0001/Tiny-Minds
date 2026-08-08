from __future__ import annotations

import json
from pathlib import Path

import pytest

import tiny_minds.services.foundry as foundry
from tiny_minds.services.foundry import FoundryManager, FoundryServiceError


def test_status_without_state_is_unmanaged(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(FoundryManager, "_healthy", staticmethod(lambda url: False))
    status = FoundryManager(tmp_path).status(9000)
    assert status == {
        "service": "foundry", "managed": False, "base_url": "http://127.0.0.1:9000", "healthy": False
    }


def test_stop_refuses_pid_or_command_mismatch(monkeypatch, tmp_path: Path) -> None:
    manager = FoundryManager(tmp_path)
    manager.state_root.mkdir(parents=True)
    manager.state_path.write_text(json.dumps({"managed": True, "pid": 42, "command_fingerprint": "wrong"}), encoding="utf-8")
    monkeypatch.setattr(FoundryManager, "_process_matches", staticmethod(lambda state: False))
    with pytest.raises(FoundryServiceError, match="Refusing to stop"):
        manager.stop()
    assert manager.state_path.exists()


def test_healthy_compatible_unmanaged_service_is_reused(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(FoundryManager, "_healthy", staticmethod(lambda url: url.endswith(":8123")))
    state = FoundryManager(tmp_path).ensure(8123)
    assert state["healthy"] is True
    assert state["managed"] is False


def test_port_collision_selects_next_available_loopback_port(monkeypatch, tmp_path: Path) -> None:
    python = tmp_path / "Tools" / "foundry-local-runtime" / "ONNX host service" / "env" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    started = {"value": False}

    class FakeProcess:
        pid = 12345

        def poll(self):
            return None

        def terminate(self):
            return None

    def fake_popen(*args, **kwargs):
        started["value"] = True
        return FakeProcess()

    monkeypatch.setattr(foundry, "_port_available", lambda port: port == 8124)
    monkeypatch.setattr(FoundryManager, "_healthy", staticmethod(lambda url: started["value"] and url.endswith(":8124")))
    monkeypatch.setattr(foundry.subprocess, "Popen", fake_popen)
    state = FoundryManager(tmp_path).ensure(8123, timeout_seconds=1)
    assert state["port"] == 8124
    assert state["managed"] is True

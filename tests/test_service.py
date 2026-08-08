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


def test_sequence_operations_validate_response_cardinality(monkeypatch, tmp_path: Path) -> None:
    manager = FoundryManager(tmp_path)
    monkeypatch.setattr(manager, "ensure_model", lambda model_id, preferred_port=8123: {"base_url": "http://127.0.0.1:8123"})

    def request(url, method="GET", payload=None, timeout=3.0):
        if url.endswith("/rerank"):
            return {"scores": [0.2, 0.8]}
        if url.endswith("/nli"):
            return {"scores": [{"contradiction": 0.1, "entailment": 0.8, "neutral": 0.1}]}
        if url.endswith("/classify"):
            return {"scores": [{"a": 0.9, "b": 0.1}]}
        raise AssertionError(url)

    monkeypatch.setattr(foundry, "_json_request", request)
    reranked, _ = manager.rerank("query", ["a", "b"], "reranker")
    inferred, _ = manager.nli([{"premise": "a", "hypothesis": "a"}], "nli")
    classified, _ = manager.classify(["a"], ["a", "b"], "nli")
    assert reranked == [0.2, 0.8]
    assert inferred[0]["entailment"] == 0.8
    assert classified[0]["a"] == 0.9

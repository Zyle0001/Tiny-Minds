from __future__ import annotations

import numpy as np

from minds.affect.model import AffectMind
from minds.context.model import ContextMind
from minds.curiosity.observer import CuriosityMind
from minds.empathy.model import EmpathyMind
from minds.intent.model import IntentMind
from minds.logic.model import LogicMind
from minds_future.ethics.model import EthicsMind
from storage.memory_store import MemoryStore
from tm_core.orchestrator import Orchestrator
from tm_core.registry import MindRegistry


def assert_mind_output(mind, payload):
    output = mind.think(payload)
    assert isinstance(output["embedding"], np.ndarray)
    assert isinstance(output["confidence"], float)
    assert isinstance(output["labels"], dict)
    assert isinstance(output["suggestions"], dict)
    assert isinstance(output["aux"], dict)


def test_stub_minds_produce_contract_outputs():
    assert_mind_output(AffectMind(), {"text": "hello"})
    assert_mind_output(IntentMind(), {"text": "hello"})
    assert_mind_output(LogicMind(), {"text": "hello"})
    affect = AffectMind().think({"text": "hello"})
    assert_mind_output(EmpathyMind(), {"mind_signals": {"affect": affect}})
    ctx_mind = ContextMind()
    ctx_mind.think({"mind_signals": {"affect": affect}})
    assert isinstance(ctx_mind.state_vector(), np.ndarray)
    memory_hits = MemoryStore().retrieve(None)
    assert_mind_output(CuriosityMind(), {"context_vec": ctx_mind.state_vector(), "memory_hits": memory_hits})
    assert_mind_output(EthicsMind(), {"text": "hello"})


def test_orchestrator_single_step_runs():
    registry = MindRegistry()
    registry.register(AffectMind())
    registry.register(IntentMind())
    registry.register(LogicMind())
    registry.register(EmpathyMind())
    registry.register(ContextMind())
    registry.register(CuriosityMind())
    registry.register(EthicsMind())
    memory_store = MemoryStore()
    orchestrator = Orchestrator(registry, memory_store, {"memory": {"top_k": 2}})
    result = orchestrator.step("Test input")
    assert "reply" in result
    assert "act" in result
    assert "debug" in result

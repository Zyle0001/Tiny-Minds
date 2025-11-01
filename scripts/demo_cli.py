"""Demo CLI running a single orchestrator turn with stub minds."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def build_registry() -> MindRegistry:
    registry = MindRegistry()
    registry.register(AffectMind())
    registry.register(IntentMind())
    registry.register(LogicMind())
    registry.register(EmpathyMind())
    registry.register(ContextMind())
    registry.register(CuriosityMind())
    registry.register(EthicsMind())
    return registry


def main(args: argparse.Namespace) -> None:
    registry = build_registry()
    memory_store = MemoryStore()
    config: Dict[str, Any] = {"memory": {"top_k": 5}}
    orchestrator = Orchestrator(registry=registry, memory_store=memory_store, config=config)
    result = orchestrator.step(args.text)
    print("Reply:", result["reply"])
    print("Action:", result["act"])
    print("--- Debug ---")
    for name, payload in result["debug"].items():
        print(name, ":", payload)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Tiny Minds demo loop")
    parser.add_argument("text", type=str, help="User utterance to process")
    main(parser.parse_args())

"""Conversation orchestrator coordinating registered minds."""
from __future__ import annotations

from typing import Any, Dict

from .registry import MindRegistry


class Orchestrator:
    """Implements the minimal execution loop across minds."""

    def __init__(self, registry: MindRegistry, memory_store: Any, config: Dict[str, Any]) -> None:
        self.registry = registry
        self.memory_store = memory_store
        self.config = config

    def step(self, user_text: str) -> Dict[str, Any]:
        context_mind = self.registry.get("context")
        ctx_vec_prev = context_mind.state_vector()
        pre_hits = self.memory_store.retrieve(query_vec=ctx_vec_prev, top_k=self.config.get("memory", {}).get("top_k", 5))

        aff = self.registry.get("affect").think({"text": user_text, "meta": {}})
        intent = self.registry.get("intent").think({"text": user_text})
        logic = self.registry.get("logic").think({"text": user_text})
        emp = self.registry.get("empathy").think({"text": user_text, "mind_signals": {"affect": aff}})

        ctx = context_mind.think({
            "mind_signals": {"affect": aff, "intent": intent, "logic": logic, "empathy": emp},
            "memory_hits": pre_hits,
        })

        post_hits = self.memory_store.retrieve(query_vec=ctx["embedding"], top_k=self.config.get("memory", {}).get("top_k", 5))
        mem_write_id = self.memory_store.maybe_write(
            text=user_text,
            vec=ctx["embedding"],
            meta={"affect": aff["labels"], "intent": intent["labels"]},
        )

        cur = self.registry.get("curiosity").think({
            "mind_signals": {"affect": aff, "intent": intent, "logic": logic},
            "context_vec": ctx["embedding"],
            "memory_hits": post_hits,
        })

        reply, act = self.simple_core_reply(user_text, aff, intent, logic, emp, ctx, cur, post_hits)
        return {
            "reply": reply,
            "act": act,
            "debug": {
                "affect": aff,
                "intent": intent,
                "logic": logic,
                "empathy": emp,
                "context": ctx,
                "curiosity": cur,
                "mem_hits": post_hits,
                "mem_write_id": mem_write_id,
            },
        }

    def simple_core_reply(self, user_text: str, aff: Dict[str, Any], intent: Dict[str, Any], logic: Dict[str, Any], emp: Dict[str, Any], ctx: Dict[str, Any], cur: Dict[str, Any], post_hits: Any) -> Any:
        intent_conf = intent.get("confidence", 0.0)
        ethics = self.registry.get("ethics") if "ethics" in self.registry else None
        safe_reply = user_text
        if ethics is not None:
            safe_reply = ethics.think({"text": user_text}).get("suggestions", {}).get("reply", user_text)
        if intent_conf >= 0.8:
            reply = f"(stub) Responding confidently to intent: {intent['labels'].get('intent', 'unknown')}"
        elif cur.get("confidence", 0.0) >= 0.6:
            reply = "(stub) I'm curious about a detail—could you clarify?"
        else:
            reply = "(stub) I think I understand, but let me know if that's right."
        return reply, {"safe_echo": safe_reply}

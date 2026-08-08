from __future__ import annotations

import hashlib
import json
from typing import Any

from .contracts import PrimitiveResult, Provenance
from .engine import ExecutionContext
from .registry import CapabilityRegistry


VERSION = "0.2.0"


def _result(capability: str, data: dict[str, Any]) -> PrimitiveResult:
    return PrimitiveResult(
        capability=capability,
        version=VERSION,
        status="success",
        data=data,
        provenance=Provenance(implementation=__name__, version=VERSION),
    )


class Sha256Primitive:
    capability = "core.hash.sha256"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        if "value" in config:
            value = config["value"]
        else:
            input_key = str(config.get("input_key", "value"))
            if input_key not in context.request.inputs:
                raise ValueError(f"Input key '{input_key}' is required")
            value = context.request.inputs[input_key]
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return _result(self.capability, {"algorithm": "sha256", "digest": hashlib.sha256(encoded).hexdigest()})


class ValidateMappingPrimitive:
    capability = "core.structure.validate-mapping"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        input_key = str(config.get("input_key", "document"))
        value = context.request.inputs.get(input_key)
        required = [str(item) for item in config.get("required", [])]
        is_mapping = isinstance(value, dict)
        missing = [key for key in required if not is_mapping or key not in value]
        return _result(self.capability, {
            "valid": is_mapping and not missing,
            "is_mapping": is_mapping,
            "missing_fields": missing,
        })


def register_core(registry: CapabilityRegistry) -> None:
    for primitive in (Sha256Primitive, ValidateMappingPrimitive):
        registry.register(primitive.capability, primitive)

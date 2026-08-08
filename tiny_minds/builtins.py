from __future__ import annotations

import hashlib
import json
from typing import Any

from .contracts import PrimitiveResult, Provenance
from .engine import CapabilityUnavailable, ExecutionContext
from .providers import ProviderUnavailable
from .registry import CapabilityRegistry


VERSION = "1.0.0"


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


class ProviderInvokePrimitive:
    capability = "core.provider.invoke"
    version = VERSION

    def execute(self, context: ExecutionContext, config: dict, dependencies: dict) -> PrimitiveResult:
        provider_id = str(config.get("provider", "default"))
        provider = context.providers.get(provider_id)
        if provider is None:
            raise CapabilityUnavailable(
                f"Provider '{provider_id}' is not configured",
                "Install and explicitly configure a compatible provider, or keep this node optional",
            )
        operation = str(config.get("operation", "invoke"))
        payload = config.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError("Provider payload must be a mapping")
        try:
            result = provider.invoke(operation, payload)
        except ProviderUnavailable as exc:
            raise CapabilityUnavailable(str(exc), exc.remediation) from exc
        return _result(self.capability, {"provider": provider_id, "operation": operation, "result": result})


def register_core(registry: CapabilityRegistry) -> None:
    for primitive in (Sha256Primitive, ValidateMappingPrimitive, ProviderInvokePrimitive):
        registry.register(primitive.capability, primitive)

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .application import build_configured_providers, build_integration_providers, build_registry, execute_pipeline
from .contracts import RunRequest
from .engine import PipelineExecutionError
from .extensions import discover_doctor_checks, discover_service_controls
from .manifest import load_manifest
from .providers import ProviderRegistry, load_runtime_config
from .telemetry import append_telemetry


def _emit(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _workspace(value: str | None) -> Path:
    return Path(value or ".").resolve()


def _manifest(workspace: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve()
    for suffix in (".yaml", ".yml"):
        path = workspace / "Cognition" / "pipelines" / f"{value}{suffix}"
        if path.exists():
            return path
    raise ValueError(f"Pipeline '{value}' was not found by path or workspace ID")


def _request_payload(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}
    raw = sys.stdin.read() if value == "-" else Path(value).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Pipeline input must be a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tiny-minds", description="Local cognitive machinery runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capabilities = subparsers.add_parser("capabilities")
    capabilities.add_argument("--integration", action="append", default=[])
    capabilities.add_argument("--config")
    capabilities.add_argument("--json", action="store_true")

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--workspace")
    doctor.add_argument("--integration", action="append", default=[])
    doctor.add_argument("--config")
    doctor.add_argument("--json", action="store_true")

    run = subparsers.add_parser("run")
    run.add_argument("pipeline")
    run.add_argument("--workspace")
    run.add_argument("--input")
    run.add_argument("--config")
    run.add_argument("--no-write", action="store_true")
    run.add_argument("--debug", action="store_true")
    run.add_argument("--json", action="store_true")

    service = subparsers.add_parser("service")
    service.add_argument("action", choices=("status", "ensure", "stop"))
    service.add_argument("service")
    service.add_argument("--workspace")
    service.add_argument("--config")
    service.add_argument("--port", type=int, default=8123)
    service.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "capabilities":
            runtime_config = load_runtime_config(Path(args.config)) if args.config else None
            _emit({
                "schema_version": 1,
                "runtime": "tiny-minds-core",
                "integrations": args.integration,
                "capabilities": build_registry(args.integration, extension_allowlist=(runtime_config.allowed_extensions if runtime_config else args.integration)).capabilities(),
            })
            return 0
        if args.command == "doctor":
            runtime_config = load_runtime_config(Path(args.config)) if args.config else None
            checks = {
                "python_supported": sys.version_info >= (3, 10),
                "core_registry": bool(build_registry().capabilities()),
            }
            if runtime_config:
                doctor_context = {"workspace": str(_workspace(args.workspace)), "config": runtime_config}
                for check_id, extension in discover_doctor_checks(runtime_config.allowed_extensions).items():
                    checks[check_id] = extension.check(doctor_context)
            integrations: dict[str, Any] = {}
            provider_checks: list[dict[str, Any]] = []
            checked_hashes: dict[str, str] = {}
            if runtime_config:
                workspace = _workspace(args.workspace)
                for provider in runtime_config.providers:
                    check: dict[str, Any] = {
                        "id": provider.id, "kind": provider.kind, "implementation": provider.implementation,
                        "configured": True,
                    }
                    if provider.implementation == "foundry":
                        model_path = workspace / "Tools" / "foundry-local-runtime" / "ONNX host service" / "models" / str(provider.model_id) / "model.onnx"
                        check["model_installed"] = model_path.is_file()
                        if model_path.is_file() and provider.model_sha256:
                            key = str(model_path)
                            if key not in checked_hashes:
                                digest = hashlib.sha256()
                                with model_path.open("rb") as stream:
                                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                                        digest.update(block)
                                checked_hashes[key] = digest.hexdigest()
                            check["checksum_matches"] = checked_hashes[key].casefold() == provider.model_sha256.casefold()
                    else:
                        check["endpoint_configured"] = bool(provider.endpoint)
                    provider_checks.append(check)
                checks["providers_ready"] = all(
                    item.get("configured", False)
                    and item.get("model_installed", item.get("endpoint_configured", True))
                    and item.get("checksum_matches", True)
                    for item in provider_checks
                )
            if "workspace-memory" in args.integration:
                workspace = _workspace(args.workspace)
                model = workspace / "Tools" / "foundry-local-runtime" / "ONNX host service" / "models" / "all-MiniLM-L6-v2" / "adapter.json"
                foundry_repo = workspace / "Tools" / "foundry-local-runtime"
                foundry_python = any(path.exists() for path in (
                    foundry_repo / "ONNX host service" / "env" / "Scripts" / "python.exe",
                    foundry_repo / ".venv" / "Scripts" / "python.exe",
                    foundry_repo / ".venv" / "bin" / "python",
                ))
                integrations["workspace-memory"] = {
                    "status": "ready" if foundry_python and model.is_file() else "degraded",
                    "workspace": workspace.is_dir(),
                    "pipeline_directory": (workspace / "Cognition" / "pipelines").is_dir(),
                    "embedding_provider": {
                        "configured": foundry_python,
                        "model_installed": model.is_file(),
                        "provider": "foundry",
                    },
                }
            check_health = all(
                value if isinstance(value, bool) else bool(value.get("healthy", value.get("status") == "ready"))
                for value in checks.values()
            )
            healthy = check_health and all(
                item.get("status") == "ready" for item in integrations.values()
            )
            _emit({
                "schema_version": 1,
                "runtime": "tiny-minds-core",
                "status": "healthy" if healthy else "degraded",
                "checks": checks,
                "providers": provider_checks,
                "integrations": integrations,
            })
            return 0 if healthy else 2
        if args.command == "service":
            workspace = _workspace(args.workspace)
            try:
                if args.service == "foundry":
                    from .services import FoundryManager, FoundryServiceError
                    manager = FoundryManager(workspace, record_telemetry=True)
                else:
                    if not args.config:
                        raise ValueError("External service controls require --config")
                    runtime_config = load_runtime_config(Path(args.config))
                    controls = discover_service_controls(runtime_config.allowed_extensions)
                    if args.service not in controls:
                        raise ValueError(f"Unknown or non-allowlisted service '{args.service}'")
                    manager = controls[args.service].factory({"workspace": workspace, "config": runtime_config})
                operation = {"status": manager.status, "ensure": manager.ensure, "stop": manager.stop}[args.action]
                payload = operation(args.port) if args.action != "stop" else operation()
            except (ImportError, RuntimeError) as exc:
                raise PipelineExecutionError(f"Optional service integration is unavailable: {exc}") from exc
            _emit(payload)
            return 0 if payload.get("healthy", True) else 2
        if args.command == "run":
            workspace = _workspace(args.workspace)
            manifest = load_manifest(_manifest(workspace, args.pipeline))
            runtime_config = load_runtime_config(Path(args.config)) if args.config else None
            payload = _request_payload(args.input)
            if any(key in payload for key in ("schema_version", "inputs", "constraints", "debug")):
                request = RunRequest.model_validate(payload)
                if args.debug:
                    request.debug = True
            else:
                request = RunRequest(inputs=payload, debug=args.debug)
            if args.no_write:
                request.inputs["no_write"] = True
            providers = build_integration_providers(
                manifest.integrations, workspace, record_telemetry=not args.no_write
            )
            if runtime_config:
                configured = build_configured_providers(
                    runtime_config, workspace=workspace, record_telemetry=not args.no_write
                )
                for provider_id in configured.providers():
                    providers.register(provider_id, configured.get(provider_id))
            result = execute_pipeline(
                manifest, request, workspace, providers,
                extension_allowlist=(runtime_config.allowed_extensions if runtime_config else None),
            )
            if not args.no_write and manifest.integrations:
                try:
                    append_telemetry(workspace, result)
                except OSError as exc:
                    result.diagnostics.append(f"Telemetry write failed: {exc}")
            _emit(result.model_dump(mode="json"))
            return 2 if result.status == "partial" else 0
    except (ValidationError, ValueError, json.JSONDecodeError, OSError) as exc:
        _emit({"schema_version": 1, "status": "error", "error_type": "invalid-request", "message": str(exc)})
        return 3
    except PipelineExecutionError as exc:
        _emit({"schema_version": 1, "status": "error", "error_type": "execution-failure", "message": str(exc)})
        return 4
    return 4


if __name__ == "__main__":
    raise SystemExit(main())

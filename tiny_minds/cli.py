from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .application import build_registry, execute_pipeline
from .contracts import RunRequest
from .engine import PipelineExecutionError
from .services import FoundryManager, FoundryServiceError
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
    capabilities.add_argument("--json", action="store_true")

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--workspace")
    doctor.add_argument("--json", action="store_true")

    run = subparsers.add_parser("run")
    run.add_argument("pipeline")
    run.add_argument("--workspace")
    run.add_argument("--input")
    run.add_argument("--no-write", action="store_true")
    run.add_argument("--debug", action="store_true")
    run.add_argument("--json", action="store_true")

    service = subparsers.add_parser("service")
    service.add_argument("action", choices=("status", "ensure", "stop"))
    service.add_argument("service", choices=("foundry",))
    service.add_argument("--workspace")
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
            _emit({"schema_version": 1, "capabilities": build_registry().capabilities()})
            return 0
        if args.command == "doctor":
            workspace = _workspace(args.workspace)
            model = workspace / "Tools" / "foundry-local-runtime" / "ONNX host service" / "models" / "all-MiniLM-L6-v2" / "adapter.json"
            foundry_repo = workspace / "Tools" / "foundry-local-runtime"
            foundry_python = any(path.exists() for path in (
                foundry_repo / "ONNX host service" / "env" / "Scripts" / "python.exe",
                foundry_repo / ".venv" / "Scripts" / "python.exe",
                foundry_repo / ".venv" / "bin" / "python",
            ))
            manifests = workspace / "Cognition" / "pipelines"
            status = FoundryManager(workspace).status()
            checks = {
                "workspace": workspace.is_dir(),
                "pipeline_directory": manifests.is_dir(),
                "minilm_installed": model.is_file(),
                "foundry_installed": foundry_python,
            }
            _emit({
                "schema_version": 1,
                "status": "healthy" if all(checks.values()) else "degraded",
                "checks": checks,
                "runtime": {"foundry_running": bool(status.get("healthy"))},
                "foundry": status,
            })
            return 0 if all(checks.values()) else 2
        if args.command == "service":
            workspace = _workspace(args.workspace)
            manager = FoundryManager(workspace, record_telemetry=True)
            operation = {"status": manager.status, "ensure": manager.ensure, "stop": manager.stop}[args.action]
            payload = operation(args.port) if args.action != "stop" else operation()
            _emit(payload)
            return 0 if payload.get("healthy", True) else 2
        if args.command == "run":
            workspace = _workspace(args.workspace)
            payload = _request_payload(args.input)
            if any(key in payload for key in ("schema_version", "inputs", "constraints", "debug")):
                request = RunRequest.model_validate(payload)
                if args.debug:
                    request.debug = True
            else:
                request = RunRequest(inputs=payload, debug=args.debug)
            if args.no_write:
                request.inputs["no_write"] = True
            result = execute_pipeline(_manifest(workspace, args.pipeline), request, workspace)
            if not args.no_write:
                try:
                    append_telemetry(workspace, result)
                except OSError as exc:
                    result.diagnostics.append(f"Telemetry write failed: {exc}")
            _emit(result.model_dump(mode="json"))
            return 2 if result.status == "partial" else 0
    except (ValidationError, ValueError, json.JSONDecodeError, OSError) as exc:
        _emit({"schema_version": 1, "status": "error", "error_type": "invalid-request", "message": str(exc)})
        return 3
    except (PipelineExecutionError, FoundryServiceError) as exc:
        _emit({"schema_version": 1, "status": "error", "error_type": "execution-failure", "message": str(exc)})
        return 4
    return 4


if __name__ == "__main__":
    raise SystemExit(main())

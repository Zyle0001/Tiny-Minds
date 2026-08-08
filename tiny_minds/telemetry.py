from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .contracts import PipelineResult


def append_telemetry(workspace: Path, result: PipelineResult) -> None:
    root = workspace / "Metrics" / "Tiny-Minds"
    root.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "run_id": result.run_id,
        "pipeline_id": result.pipeline.id,
        "pipeline_version": result.pipeline.version,
        "status": result.status,
        "disposition": result.disposition,
        "duration_ms": result.metrics.get("duration_ms", 0),
        "candidate_count": result.metrics.get("candidate_count", 0),
        "capabilities": {
            node_id: {
                "capability": item.capability,
                "version": item.version,
                "status": item.status,
                "duration_ms": item.metrics.duration_ms,
                "cache_hits": item.metrics.cache_hits,
                "cache_misses": item.metrics.cache_misses,
                "candidate_count": item.metrics.candidate_count,
                "error_count": len(item.diagnostics),
            }
            for node_id, item in result.primitives.items()
        },
    }
    ledger = root / "events.jsonl"
    with ledger.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n")
    _write_summary(workspace / "Metrics" / "Tiny-Minds.md", ledger)


def append_service_telemetry(workspace: Path, action: str, payload: dict) -> None:
    root = workspace / "Metrics" / "Tiny-Minds"
    root.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "event_type": "service-lifecycle",
        "service": "foundry",
        "action": action,
        "managed": bool(payload.get("managed", False)),
        "healthy": bool(payload.get("healthy", False)),
        "pid": payload.get("pid"),
        "port": payload.get("port"),
    }
    ledger = root / "events.jsonl"
    with ledger.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n")
    _write_summary(workspace / "Metrics" / "Tiny-Minds.md", ledger)


def _write_summary(path: Path, ledger: Path) -> None:
    events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    pipeline_events = [item for item in events if item.get("event_type", "pipeline-run") == "pipeline-run"]
    service_events = [item for item in events if item.get("event_type") == "service-lifecycle"]
    total_duration = sum(int(item.get("duration_ms", 0)) for item in pipeline_events)
    dispositions: dict[str, int] = {}
    for item in pipeline_events:
        key = item.get("disposition", "unknown")
        dispositions[key] = dispositions.get(key, 0) + 1
    lines = [
        "# Tiny Minds Metrics", "",
        "This derived view contains metadata only. Raw source text and vectors are never retained here.", "",
        f"- Runs: {len(pipeline_events)}",
        f"- Service lifecycle events: {len(service_events)}",
        f"- Total runtime: {total_duration} ms",
        f"- Last event: {events[-1]['recorded_at'] if events else '-'}", "",
        "## Dispositions", "",
        "| disposition | runs |", "| --- | ---: |",
    ]
    lines.extend(f"| {key} | {count} |" for key, count in sorted(dispositions.items()))
    temporary = path.with_suffix(".md.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)

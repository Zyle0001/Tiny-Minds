from __future__ import annotations

import json
from pathlib import Path

from tiny_minds.contracts import PipelineIdentity, PipelineResult, PrimitiveResult, Provenance
from tiny_minds.telemetry import append_telemetry


def test_telemetry_is_metadata_only_and_summary_location_is_stable(tmp_path: Path) -> None:
    secret = "RAW-CONTENT-MUST-NOT-LEAK"
    primitive = PrimitiveResult(
        capability="test",
        version="1",
        status="success",
        data={"raw": secret},
        provenance=Provenance(implementation="test", version="1", model_sha256="abc123"),
    )
    result = PipelineResult(
        run_id="run-1",
        pipeline=PipelineIdentity(id="test", version="1"),
        status="success",
        disposition="resolved",
        primitives={"node": primitive},
    )
    append_telemetry(tmp_path, result)
    ledger = tmp_path / "Metrics" / "Tiny-Minds" / "events.jsonl"
    summary = tmp_path / "Metrics" / "Tiny-Minds.md"
    assert ledger.exists() and summary.exists()
    raw = ledger.read_text(encoding="utf-8")
    assert secret not in raw
    event = json.loads(raw)
    assert event["pipeline_id"] == "test"

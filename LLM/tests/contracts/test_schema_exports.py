"""Generated JSON Schema snapshot tests."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from operational_decision.contracts.final_output import FinalDecisionOutput
from operational_decision.contracts.upstream_vlm import UpstreamVLMOutput
from operational_decision.contracts.visual import FinalVisualEvidencePackage


@pytest.mark.parametrize(
    ("model", "path"),
    [
        (UpstreamVLMOutput, Path("data/schemas/upstream_vlm_output.schema.json")),
        (
            FinalVisualEvidencePackage,
            Path("data/schemas/final_visual_evidence.schema.json"),
        ),
        (FinalDecisionOutput, Path("data/schemas/final_decision_output.schema.json")),
    ],
)
def test_schema_snapshot(model: type[BaseModel], path: Path) -> None:
    """Each checked-in schema equals its Pydantic model export."""
    assert json.loads(path.read_text(encoding="utf-8")) == model.model_json_schema()

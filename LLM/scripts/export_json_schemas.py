"""Export versioned Pydantic contracts as deterministic JSON Schema files."""

import json
from pathlib import Path

from pydantic import BaseModel

from operational_decision.contracts.final_output import FinalDecisionOutput
from operational_decision.contracts.upstream_vlm import UpstreamVLMOutput
from operational_decision.contracts.visual import FinalVisualEvidencePackage

SCHEMAS: tuple[tuple[type[BaseModel], Path], ...] = (
    (UpstreamVLMOutput, Path("data/schemas/upstream_vlm_output.schema.json")),
    (FinalVisualEvidencePackage, Path("data/schemas/final_visual_evidence.schema.json")),
    (FinalDecisionOutput, Path("data/schemas/final_decision_output.schema.json")),
)


def export_json_schemas() -> None:
    """Write all required schema snapshots from their Pydantic models."""
    for model, path in SCHEMAS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    export_json_schemas()

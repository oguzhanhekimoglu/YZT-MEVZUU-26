"""Analyze request contracts."""

from typing import Literal

from pydantic import Field

from operational_decision.contracts.common import StrictContract
from operational_decision.contracts.visual import FinalVisualEvidencePackage


class GPUHandoff(StrictContract):
    """Sequential GPU ownership signal supplied with an analyze request."""

    visual_pipeline_status: Literal["COMPLETED"]
    gpu_release_status: str = Field(min_length=1, max_length=50)


class AnalyzeEventRequest(StrictContract):
    """Canonical request accepted by the future analyze endpoint."""

    video_id: str = Field(min_length=1, max_length=150)
    explanation_requested: bool = False
    gpu_handoff: GPUHandoff
    visual_evidence: FinalVisualEvidencePackage
    request_metadata: dict[str, object] | None = None

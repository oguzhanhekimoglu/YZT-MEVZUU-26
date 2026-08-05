"""Canonical visual evidence contracts."""

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from operational_decision.contracts.common import (
    ConfidenceOrigin,
    EvidenceSourceMode,
    StrictContract,
    UncertaintyLevel,
    VisualClass,
    VisualEvidenceStatus,
)
from operational_decision.contracts.upstream_vlm import UpstreamVLMOutput
from operational_decision.contracts.video_events import VideoEventProjection


def _require_aware_datetime(value: datetime) -> datetime:
    """Reject timestamps without a usable UTC offset."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class VisualCandidate(StrictContract):
    """One ranked upstream visual retrieval candidate."""

    rank: int = Field(ge=1)
    candidate_name: str = Field(min_length=1, max_length=200)
    score: float = Field(ge=0.0, le=1.0)
    source_ref: str | None = Field(default=None, min_length=1, max_length=300)


class TrackTiming(StrictContract):
    """Observation offsets relative to video start."""

    first_seen_offset_seconds: float = Field(ge=0.0)
    last_seen_offset_seconds: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Ensure the observation interval is ordered."""
        if self.last_seen_offset_seconds < self.first_seen_offset_seconds:
            raise ValueError("last_seen_offset_seconds must be >= first_seen_offset_seconds")
        return self


class TrackMetrics(StrictContract):
    """Tracking metrics supplied by the upstream tracking subsystem."""

    track_duration_seconds: float = Field(ge=0.0)
    track_stability: float = Field(ge=0.0, le=1.0)
    detection_count: int = Field(ge=1)
    average_detection_confidence: float = Field(ge=0.0, le=1.0)


class CropEvidenceSummary(StrictContract):
    """References and upstream quality measures for selected crops."""

    selected_crop_count: int = Field(ge=0)
    selected_crop_refs: list[str] = Field(default_factory=list)
    crop_quality_scores: list[float] = Field(default_factory=list)
    average_crop_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    view_diversity_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_cardinality(self) -> Self:
        """Keep crop count, references, and score lists aligned."""
        if self.selected_crop_count != len(self.selected_crop_refs):
            raise ValueError("selected_crop_count must equal selected_crop_refs length")
        if len(self.selected_crop_refs) != len(self.crop_quality_scores):
            raise ValueError("crop refs and quality scores must have equal length")
        return self


class ProducerMetadata(StrictContract):
    """Version and provenance metadata supplied by the visual producer."""

    visual_pipeline_version: str = Field(min_length=1, max_length=150)
    vlm_model: str = Field(min_length=1, max_length=200)
    retrieval_model: str | None = Field(default=None, min_length=1, max_length=200)
    created_at_utc: datetime

    _aware_created_at = field_validator("created_at_utc")(_require_aware_datetime)


class UpstreamTrackContext(StrictContract):
    """Tracking facts required to adapt a raw VLM result."""

    track_id: str = Field(min_length=1, max_length=150)
    first_seen_offset_seconds: float = Field(ge=0.0)
    last_seen_offset_seconds: float = Field(ge=0.0)
    track_duration_seconds: float = Field(ge=0.0)
    track_stability: float = Field(ge=0.0, le=1.0)
    detection_count: int = Field(ge=1)
    average_detection_confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Ensure upstream track offsets are ordered."""
        if self.last_seen_offset_seconds < self.first_seen_offset_seconds:
            raise ValueError("last_seen_offset_seconds must be >= first_seen_offset_seconds")
        return self


class FinalVisualEvidencePackage(StrictContract):
    """Canonical visual wrapper accepted by the analyze endpoint."""

    schema_version: Literal["visual-evidence/1.1"] = "visual-evidence/1.1"
    evidence_source_mode: EvidenceSourceMode
    track_id: str = Field(min_length=1, max_length=150)
    visual_class: VisualClass
    final_visual_hypothesis: str | None = Field(default=None, min_length=1, max_length=200)
    candidate_matches: list[VisualCandidate] = Field(default_factory=list)
    visual_evidence_status: VisualEvidenceStatus
    visual_confidence: float = Field(ge=0.0, le=1.0)
    confidence_origin: ConfidenceOrigin
    uncertainty_level: UncertaintyLevel
    uncertainty_flags: list[str] = Field(default_factory=list)
    human_visual_review_required: bool
    track_metrics: TrackMetrics | None = None
    crop_evidence_summary: CropEvidenceSummary | None = None
    timing: TrackTiming
    upstream_vlm_output: UpstreamVLMOutput
    producer_metadata: ProducerMetadata
    video_event_projection: VideoEventProjection = Field(default_factory=VideoEventProjection)

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        """Enforce cross-field canonical and VLM-only safety rules."""
        if self.visual_class is not VisualClass.NON_AIRCRAFT and not self.final_visual_hypothesis:
            raise ValueError("final_visual_hypothesis is required for aircraft classes")
        ranks = [candidate.rank for candidate in self.candidate_matches]
        if len(ranks) != len(set(ranks)):
            raise ValueError("candidate ranks must be unique")
        if self.evidence_source_mode is EvidenceSourceMode.VLM_ONLY:
            if self.uncertainty_level is UncertaintyLevel.LOW:
                raise ValueError("VLM_ONLY uncertainty must be MEDIUM or HIGH")
            if not self.human_visual_review_required:
                raise ValueError("VLM_ONLY requires human visual review")
            if self.confidence_origin is not ConfidenceOrigin.VLM_SELF_REPORTED:
                raise ValueError("VLM_ONLY confidence origin must be VLM_SELF_REPORTED")
            if self.visual_evidence_status is VisualEvidenceStatus.SUPPORTED:
                raise ValueError("VLM_ONLY evidence cannot be SUPPORTED")
        elif not self.candidate_matches:
            raise ValueError("retrieval or fused evidence requires candidate matches")
        return self

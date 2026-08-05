"""Contract tests for canonical visual evidence."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from operational_decision.contracts.visual import FinalVisualEvidencePackage

FIXTURE = Path("tests/fixtures/visual_packages/valid_wrapper_v1_1.json")


def load_payload() -> dict[str, object]:
    """Load a mutable canonical visual fixture."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def validate(payload: dict[str, object]) -> FinalVisualEvidencePackage:
    """Validate a Python payload through the external JSON boundary."""
    return FinalVisualEvidencePackage.model_validate_json(json.dumps(payload))


def test_valid_wrapper() -> None:
    """The canonical v1.1 wrapper validates."""
    assert validate(load_payload()).track_id == "TRK_001"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("uncertainty_level", "LOW"),
        ("human_visual_review_required", False),
        ("visual_evidence_status", "SUPPORTED"),
    ],
)
def test_vlm_only_safety_policy(field: str, value: object) -> None:
    """VLM-only evidence cannot relax mandatory safety constraints."""
    payload = load_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        validate(payload)


def test_missing_track_id_is_rejected() -> None:
    """Track identity is mandatory."""
    payload = load_payload()
    del payload["track_id"]
    with pytest.raises(ValidationError):
        validate(payload)


def test_unknown_enum_is_rejected() -> None:
    """Unknown canonical enum values are not normalized silently."""
    payload = load_payload()
    payload["visual_class"] = "JET"
    with pytest.raises(ValidationError):
        validate(payload)


def test_unknown_field_is_rejected() -> None:
    """Unknown wrapper fields are rejected."""
    payload = load_payload()
    payload["unexpected"] = "value"
    with pytest.raises(ValidationError):
        validate(payload)


def test_naive_datetime_is_rejected() -> None:
    """Producer timestamps must be timezone-aware."""
    payload = load_payload()
    payload["producer_metadata"]["created_at_utc"] = "2026-08-10T11:20:08"
    with pytest.raises(ValidationError):
        validate(payload)


@pytest.mark.parametrize("field", ["first_seen_offset_seconds", "last_seen_offset_seconds"])
def test_negative_offsets_are_rejected(field: str) -> None:
    """Track timing offsets cannot be negative."""
    payload = load_payload()
    payload["timing"][field] = -0.1
    with pytest.raises(ValidationError):
        validate(payload)


def test_reverse_timing_is_rejected() -> None:
    """The final observation cannot precede the first observation."""
    payload = load_payload()
    payload["timing"]["last_seen_offset_seconds"] = 1.0
    with pytest.raises(ValidationError):
        validate(payload)


def test_aircraft_requires_hypothesis() -> None:
    """Every non-NON_AIRCRAFT class requires a hypothesis."""
    payload = load_payload()
    payload["final_visual_hypothesis"] = None
    with pytest.raises(ValidationError):
        validate(payload)


def test_duplicate_candidate_ranks_are_rejected() -> None:
    """Candidate ranks must be unique."""
    payload = load_payload()
    payload["evidence_source_mode"] = "VLM_PLUS_RETRIEVAL"
    payload["confidence_origin"] = "UPSTREAM_FUSION"
    payload["candidate_matches"] = [
        {"rank": 1, "candidate_name": "F-16", "score": 0.9},
        {"rank": 1, "candidate_name": "F-18", "score": 0.8},
    ]
    with pytest.raises(ValidationError):
        validate(payload)


def test_crop_refs_and_scores_must_align() -> None:
    """Crop references and quality score cardinalities must match."""
    payload = load_payload()
    payload["crop_evidence_summary"]["crop_quality_scores"] = [0.8]
    with pytest.raises(ValidationError):
        validate(payload)


def test_unsupported_wrapper_version_is_rejected() -> None:
    """Undefined legacy wrapper versions are rejected."""
    payload = load_payload()
    payload["schema_version"] = "visual-evidence/1.0"
    with pytest.raises(ValidationError):
        validate(payload)

"""Integration tests for raw VLM adaptation and invalid output."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from operational_decision.contracts.common import DecisionCode, EventStatus, RiskLevel
from operational_decision.contracts.visual import ProducerMetadata, UpstreamTrackContext
from operational_decision.input.upstream_vlm_adapter import (
    map_upstream_vlm_to_canonical,
    validate_upstream_vlm_payload,
)
from operational_decision.validation.input_validator import (
    ValidationIssue,
    build_invalid_input_output,
)

FIXTURES = Path("tests/fixtures/upstream_vlm")


def test_legacy_turkish_payload_maps_to_canonical() -> None:
    """Legacy Turkish keys are accepted only through the explicit adapter."""
    raw = json.loads((FIXTURES / "legacy_turkish_keys.json").read_text("utf-8"))
    validated = validate_upstream_vlm_payload(raw)
    canonical = map_upstream_vlm_to_canonical(
        raw_vlm=validated,
        track_context=UpstreamTrackContext(
            track_id="TRK_001",
            first_seen_offset_seconds=8.2,
            last_seen_offset_seconds=15.6,
            track_duration_seconds=7.4,
            track_stability=0.84,
            detection_count=26,
            average_detection_confidence=0.76,
        ),
        producer_metadata=ProducerMetadata.model_validate_json(
            '{"visual_pipeline_version":"temporary-contract/1.1",'
            '"vlm_model":"UPSTREAM_PROVIDED","retrieval_model":null,'
            '"created_at_utc":"2026-08-10T11:20:08Z"}'
        ),
    )
    assert canonical.visual_confidence == 0.85
    assert canonical.final_visual_hypothesis == "F-16-like"
    assert canonical.upstream_vlm_output.tehdit_seviyesi == "YUKSEK"
    assert not hasattr(canonical, "upstream_threat_advisory")
    assert not hasattr(canonical, "deprecated_destination_hypothesis")


def test_invalid_raw_confidence_is_rejected() -> None:
    """Raw confidence above 100 fails before adaptation."""
    raw = json.loads((FIXTURES / "invalid_confidence.json").read_text("utf-8"))
    with pytest.raises(ValidationError):
        validate_upstream_vlm_payload(raw)


def test_invalid_input_produces_safe_final_output() -> None:
    """Invalid input uses the shared final contract and mandatory safe values."""
    output = build_invalid_input_output(
        event_id="evt_123",
        request_id="req_123",
        errors=[ValidationIssue(code="INVALID_TRACK", message="track_id eksik")],
    )
    assert output.event_status is EventStatus.REJECTED_INVALID_INPUT
    assert output.decision is DecisionCode.INDETERMINATE
    assert output.risk_level is RiskLevel.UNKNOWN
    assert output.minimum_risk_level is RiskLevel.UNKNOWN
    assert output.human_approval_required is True
    assert output.track_id is None

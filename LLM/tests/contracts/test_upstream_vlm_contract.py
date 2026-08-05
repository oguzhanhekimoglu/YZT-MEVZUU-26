"""Contract tests for the raw upstream VLM payload."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from operational_decision.contracts.upstream_vlm import UpstreamVLMOutput

FIXTURES = Path("tests/fixtures/upstream_vlm")


def test_valid_raw_vlm_payload() -> None:
    """The supported raw payload version validates from JSON."""
    model = UpstreamVLMOutput.model_validate_json(
        (FIXTURES / "valid_vlm_only.json").read_text(encoding="utf-8")
    )
    assert model.guven_skoru == 85


@pytest.mark.parametrize(
    "filename",
    ["invalid_confidence.json", "missing_analysis.json"],
)
def test_invalid_raw_vlm_payloads(filename: str) -> None:
    """Invalid confidence and missing analysis are rejected."""
    with pytest.raises(ValidationError):
        UpstreamVLMOutput.model_validate_json((FIXTURES / filename).read_text(encoding="utf-8"))


def test_unknown_raw_field_is_rejected() -> None:
    """External contracts reject unknown fields."""
    payload = (FIXTURES / "valid_vlm_only.json").read_text(encoding="utf-8")
    with pytest.raises(ValidationError):
        UpstreamVLMOutput.model_validate_json(payload[:-2] + ', "extra": true}')


def test_unsupported_raw_schema_version_is_rejected() -> None:
    """Only upstream-vlm/1.0 is accepted."""
    payload = (FIXTURES / "valid_vlm_only.json").read_text(encoding="utf-8")
    with pytest.raises(ValidationError):
        UpstreamVLMOutput.model_validate_json(
            payload.replace("upstream-vlm/1.0", "upstream-vlm/0.9")
        )

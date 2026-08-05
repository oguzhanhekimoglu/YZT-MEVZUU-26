"""Raw-VLM context alignment and deterministic fallback acceptance tests."""
# ruff: noqa: D103

from pathlib import Path

import pytest

from tests._phase7_support import build_harness, scenario_payload

ROOT = Path(__file__).resolve().parents[2]
MISMATCH = "PLATFORM_CONTEXT_MISMATCH"


def _mq9_payload(video_id: str, track_suffix: str) -> dict[str, object]:
    payload = scenario_payload(ROOT, 18)
    payload["video_id"] = video_id
    payload["visual_evidence"]["track_id"] = f"TRK_MQ9_{track_suffix}"
    return payload


@pytest.mark.asyncio
async def test_mq9_with_general_context_has_no_platform_context_mismatch(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)

    outcome = await harness.orchestrator.analyze(_mq9_payload("VIDEO_006", "GENERAL"))

    assert outcome.output is not None
    assert outcome.output["matched_platform"] == "MQ-9 Reaper"
    assert outcome.output["risk_level"] == "HIGH"
    assert outcome.output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
    assert MISMATCH not in outcome.output["operational_consistency_flags"]


@pytest.mark.asyncio
async def test_mq9_with_expected_f35_emits_review_only_mismatch(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)

    outcome = await harness.orchestrator.analyze(_mq9_payload("VIDEO_017", "F35_CONTEXT"))

    assert outcome.output is not None
    assert MISMATCH in outcome.output["operational_consistency_flags"]
    assert MISMATCH in outcome.output["human_review_reasons"]
    assert outcome.output["human_approval_required"] is True
    assert outcome.output["risk_level"] == "HIGH"
    assert outcome.output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
    assert outcome.output["hostile_target_confirmed"] is False
    assert outcome.output["legal_violation_confirmed"] is False


@pytest.mark.asyncio
async def test_f35a_matches_its_expected_context_and_ready_scn17_package(tmp_path: Path) -> None:
    harness = await build_harness(ROOT, tmp_path)

    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 17))

    assert outcome.output is not None
    assert outcome.output["matched_platform"] == "F-35A Lightning II"
    assert MISMATCH not in outcome.output["operational_consistency_flags"]
    assert outcome.output["risk_level"] == "HIGH"
    assert outcome.output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"


@pytest.mark.asyncio
async def test_unregistered_military_policy_survives_two_invalid_llm_outputs(
    tmp_path: Path,
) -> None:
    harness = await build_harness(ROOT, tmp_path, outputs=["bad", "still bad"])

    outcome = await harness.orchestrator.analyze(scenario_payload(ROOT, 18))

    assert outcome.output is not None
    assert outcome.output["risk_level"] == "HIGH"
    assert outcome.output["decision"] == "UNREGISTERED_MILITARY_AIRCRAFT"
    assert "Sonuç insan incelemesi olmadan belirlenemedi" not in outcome.output["summary_tr"]
    assert "Türkiye Envanterinde kayıtlı olmayan askerî hava aracı" in outcome.output["summary_tr"]

"""Deterministic TEKNOFEST presentation formatter tests."""
# ruff: noqa: D103

from math import inf, nan

import pytest

from operational_decision.contracts.common import (
    DecisionCode,
    EventStatus,
    RiskLevel,
    VisualClass,
)
from operational_decision.contracts.final_output import FinalDecisionOutput
from operational_decision.contracts.llm import RecommendedAction
from operational_decision.contracts.risk import ActionCatalog, ActionDefinition
from operational_decision.contracts.video_events import UntimestampedVisualAssessment
from operational_decision.presentation.teknofest import TeknofestSpecFormatter, format_event_time


def _catalog() -> ActionCatalog:
    return ActionCatalog(
        actions=[
            ActionDefinition(
                code="CATALOG_ACTION",
                title_tr="Katalog başlığı",
                allowed_risks=[RiskLevel.LOW],
            )
        ]
    )


def _canonical(
    risk: RiskLevel,
    *,
    visual_hypothesis: str | None = "F-16-like",
    visual_class: VisualClass | None = VisualClass.FIGHTER_JET,
    actions: list[RecommendedAction] | None = None,
) -> FinalDecisionOutput:
    return FinalDecisionOutput(
        event_id="event-1",
        request_id="request-1",
        event_status=EventStatus.FINALIZED,
        visual_class=visual_class,
        visual_hypothesis=visual_hypothesis,
        decision=DecisionCode.INDETERMINATE,
        risk_level=risk,
        minimum_risk_level=risk,
        summary_tr="Canonical özet",
        recommended_actions=actions or [],
        human_approval_required=False,
    )


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (None, "00:00"),
        (-1.0, "00:00"),
        (nan, "00:00"),
        (inf, "00:00"),
        (-inf, "00:00"),
        (0.0, "00:00"),
        (65.9, "01:05"),
    ],
)
def test_legacy_event_time_formatting_is_retained(offset: float | None, expected: str) -> None:
    assert format_event_time(offset) == expected


@pytest.mark.parametrize(
    ("risk", "expected"),
    [
        (RiskLevel.LOW, "Düşük"),
        (RiskLevel.MEDIUM, "Orta"),
        (RiskLevel.HIGH, "Yüksek"),
        (RiskLevel.CRITICAL, "Kritik"),
        (RiskLevel.UNKNOWN, "Bilinmiyor"),
    ],
)
def test_all_risk_levels_have_fixed_turkish_labels(risk: RiskLevel, expected: str) -> None:
    result = TeknofestSpecFormatter(_catalog()).format(
        _canonical(risk), first_seen_offset_seconds=8.2
    )
    assert result.risk == expected


def test_legacy_scenario_event_and_action_label_precedence() -> None:
    actions = [
        RecommendedAction(action_code="CATALOG_ACTION", priority=1, reason_tr="Reason ignored"),
        RecommendedAction(action_code="REASON_ACTION", priority=2, reason_tr="Gerekçe"),
        RecommendedAction(action_code="CODE_ACTION", priority=3, reason_tr=" "),
    ]
    result = TeknofestSpecFormatter(_catalog()).format(
        _canonical(RiskLevel.LOW, actions=actions),
        first_seen_offset_seconds=65.9,
    )
    assert result.summary == "Canonical özet"
    assert result.events[0].time == "01:05"
    assert result.events[0].event == "F-16-like"
    assert result.actions == ["Katalog başlığı", "Gerekçe", "CODE_ACTION"]


def test_raw_vlm_without_event_timestamps_has_no_teknofest_event() -> None:
    canonical = _canonical(RiskLevel.LOW).model_copy(
        update={
            "untimestamped_visual_assessment": UntimestampedVisualAssessment(
                description_tr="Zamansız görsel değerlendirme."
            )
        }
    )

    result = TeknofestSpecFormatter(_catalog()).format(
        canonical,
        first_seen_offset_seconds=0.0,
    )

    assert result.events == []

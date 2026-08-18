"""TEKNOFEST presentation schema and deterministic canonical formatter."""

from math import isfinite

from pydantic import Field

from operational_decision.contracts.common import RiskLevel, StrictContract, VisualClass
from operational_decision.contracts.final_output import FinalDecisionOutput
from operational_decision.contracts.risk import ActionCatalog


class TeknofestEvent(StrictContract):
    """One compact event in the TEKNOFEST presentation contract."""

    time: str = Field(pattern=r"^\d{2,}:[0-5]\d$")
    event: str = Field(min_length=1, max_length=200)


class TeknofestSpecOutput(StrictContract):
    """Presentation-only TEKNOFEST response derived from a canonical final output."""

    summary: str = Field(min_length=1, max_length=4000)
    events: list[TeknofestEvent] = Field(default_factory=list)
    risk: str = Field(min_length=1, max_length=20)
    actions: list[str] = Field(default_factory=list)


_VISUAL_CLASS_LABELS = {
    VisualClass.UAV: "İHA",
    VisualClass.UCAV: "SİHA",
}

_RISK_LABELS = {
    RiskLevel.LOW: "Düşük",
    RiskLevel.MEDIUM: "Orta",
    RiskLevel.HIGH: "Yüksek",
    RiskLevel.CRITICAL: "Kritik",
    RiskLevel.UNKNOWN: "Bilinmiyor",
}


def format_event_time(offset_seconds: float | None) -> str:
    """Format a safe non-negative first-seen offset as truncated MM:SS."""
    if offset_seconds is None or not isfinite(offset_seconds) or offset_seconds < 0:
        return "00:00"
    whole_seconds = int(offset_seconds)
    minutes, seconds = divmod(whole_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


class TeknofestSpecFormatter:
    """Project canonical facts into the fixed TEKNOFEST presentation schema."""

    def __init__(self, action_catalog: ActionCatalog) -> None:
        """Index existing catalog labels without creating new actions."""
        self._action_titles = {
            action.code: action.title_tr.strip()
            for action in action_catalog.actions
            if action.title_tr.strip()
        }

    def format(
        self,
        canonical: FinalDecisionOutput,
        *,
        first_seen_offset_seconds: float | None,
    ) -> TeknofestSpecOutput:
        """Format canonical summary, risk, actions, and only safe legacy event timing."""
        event_name = (
            canonical.visual_hypothesis
            or (
                _VISUAL_CLASS_LABELS.get(canonical.visual_class, canonical.visual_class.value)
                if canonical.visual_class is not None
                else None
            )
            or "Operasyonel Olay Tespiti"
        )
        actions = [
            self._action_titles.get(action.action_code)
            or action.reason_tr.strip()
            or action.action_code
            for action in canonical.recommended_actions
        ]
        video_event_projection_present = (
            canonical.timestamps_available or canonical.untimestamped_visual_assessment is not None
        )
        events = (
            []
            if video_event_projection_present
            else [
                TeknofestEvent(
                    time=format_event_time(first_seen_offset_seconds),
                    event=event_name,
                )
            ]
        )
        return TeknofestSpecOutput(
            summary=canonical.summary_tr,
            events=events,
            risk=_RISK_LABELS[canonical.risk_level],
            actions=actions,
        )

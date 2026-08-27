"""TEKNOFEST presentation schema and deterministic canonical formatter."""

from math import isfinite

from pydantic import Field

from operational_decision.contracts.common import (
    DecisionCode,
    FlightPlanStatus,
    InventoryStatus,
    NotamStatus,
    PermissionStatus,
    RiskLevel,
    StrictContract,
    VisualClass,
)
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
    # Additive step-detail fields for the analysis-process UI (analysis
    # progress panel) — the compact summary/risk/actions triplet above stays
    # unchanged for existing consumers (e.g. the final decision card).
    decision: str = Field(min_length=1, max_length=100)
    inventory_status: str = Field(min_length=1, max_length=60)
    permission_status: str = Field(min_length=1, max_length=60)
    flight_plan_status: str = Field(min_length=1, max_length=60)
    notam_status: str = Field(min_length=1, max_length=60)
    human_review_required: bool
    risk_increasing_factors: list[str] = Field(default_factory=list)
    risk_reducing_factors: list[str] = Field(default_factory=list)


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

_DECISION_LABELS = {
    DecisionCode.AUTHORIZED_OPERATIONAL_MATCH: "Operasyonel kayıtlarla uyumlu yetkili operasyon",
    DecisionCode.PARTIALLY_VERIFIED_OPERATION: "Operasyon kısmen doğrulandı",
    DecisionCode.UNVERIFIED_AIRCRAFT: "Hava aracı operasyonel olarak doğrulanamadı",
    DecisionCode.OPERATIONAL_AUTHORIZATION_UNVERIFIED: "Operasyonel yetkilendirme doğrulanamadı",
    DecisionCode.UNREGISTERED_MILITARY_AIRCRAFT: (
        "Türkiye Envanterinde kayıtlı olmayan askerî hava aracı"
    ),
    DecisionCode.UNEXPECTED_PLATFORM: "Operasyon bağlamında beklenmeyen platform",
    DecisionCode.EXPIRED_OR_INVALID_PERMISSION: "Uçuş izni geçersiz veya süresi dolmuş",
    DecisionCode.ACTIVE_NOTAM_PROHIBITION: "Aktif NOTAM operasyonu yasaklıyor",
    DecisionCode.CONFLICTING_OPERATIONAL_RECORDS: "Operasyonel kayıtlar birbiriyle çelişiyor",
    DecisionCode.PLATFORM_UNRESOLVED: "Platform çözümlenemedi",
    DecisionCode.NON_AIRCRAFT: "Hava aracı olmayan hedef",
    DecisionCode.INDETERMINATE: "Sonuç insan incelemesi olmadan belirlenemedi",
    DecisionCode.REJECTED_OUT_OF_SCOPE: "Türkiye Envanteri kapsamı dışında",
}

_INVENTORY_LABELS = {
    InventoryStatus.CONFIRMED: "Envanterde kayıtlı",
    InventoryStatus.NOT_LISTED: "Envanterde kayıtlı değil",
    InventoryStatus.UNKNOWN: "Envanter sonucu belirlenemedi",
    InventoryStatus.NOT_APPLICABLE: "Envanter kontrolü uygulanmadı",
}

_PERMISSION_LABELS = {
    PermissionStatus.VALID: "Geçerli izin bulundu",
    PermissionStatus.NOT_FOUND: "İzin kaydı bulunamadı",
    PermissionStatus.EXPIRED: "İzin süresi dolmuş",
    PermissionStatus.NOT_YET_VALID: "İzin henüz geçerli değil",
    PermissionStatus.REVOKED: "İzin iptal edilmiş",
    PermissionStatus.AMBIGUOUS: "İzin kaydı belirsiz",
    PermissionStatus.CONFLICTING: "İzin kayıtları çelişkili",
    PermissionStatus.NOT_APPLICABLE: "İzin kontrolü uygulanmadı",
}

_FLIGHT_PLAN_LABELS = {
    FlightPlanStatus.FILED: "Uçuş planı dosyalandı",
    FlightPlanStatus.NOT_FOUND: "Uçuş planı bulunamadı",
    FlightPlanStatus.EXPIRED: "Uçuş planı süresi dolmuş",
    FlightPlanStatus.NOT_YET_ACTIVE: "Uçuş planı henüz aktif değil",
    FlightPlanStatus.CANCELLED: "Uçuş planı iptal edilmiş",
    FlightPlanStatus.AMBIGUOUS: "Uçuş planı belirsiz",
    FlightPlanStatus.CONFLICTING: "Uçuş planları çelişkili",
    FlightPlanStatus.NOT_APPLICABLE: "Uçuş planı kontrolü uygulanmadı",
}

_NOTAM_LABELS = {
    NotamStatus.ACTIVE_RELEVANT: "İlgili aktif NOTAM var",
    NotamStatus.ACTIVE_NOT_RELEVANT: "Aktif NOTAM var, operasyonla ilgisiz",
    NotamStatus.NONE_ACTIVE: "Aktif NOTAM yok",
    NotamStatus.EXPIRED_ONLY: "Yalnızca süresi dolmuş NOTAM var",
    NotamStatus.NOT_YET_ACTIVE: "NOTAM henüz aktif değil",
    NotamStatus.AMBIGUOUS: "NOTAM durumu belirsiz",
    NotamStatus.CONFLICTING: "NOTAM kayıtları çelişkili",
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
            decision=_DECISION_LABELS[canonical.decision],
            inventory_status=(
                _INVENTORY_LABELS[canonical.inventory_status]
                if canonical.inventory_status is not None
                else "Envanter kontrolü çalıştırılmadı"
            ),
            permission_status=(
                _PERMISSION_LABELS[canonical.permission_status]
                if canonical.permission_status is not None
                else "Uçuş izni kontrolü çalıştırılmadı"
            ),
            flight_plan_status=(
                _FLIGHT_PLAN_LABELS[canonical.flight_plan_status]
                if canonical.flight_plan_status is not None
                else "Uçuş planı kontrolü çalıştırılmadı"
            ),
            notam_status=(
                _NOTAM_LABELS[canonical.notam_status]
                if canonical.notam_status is not None
                else "NOTAM kontrolü çalıştırılmadı"
            ),
            human_review_required=canonical.human_approval_required,
            risk_increasing_factors=canonical.risk_increasing_factors,
            risk_reducing_factors=canonical.risk_reducing_factors,
        )

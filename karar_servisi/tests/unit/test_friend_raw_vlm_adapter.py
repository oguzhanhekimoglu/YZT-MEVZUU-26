"""Friend-team selective raw VLM adapter tests."""
# ruff: noqa: D103

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from operational_decision.contracts.common import UncertaintyLevel, VisualClass
from operational_decision.contracts.raw_vlm import RawVLMAdapterRequest, RawVLMOutput
from operational_decision.input.upstream_vlm_adapter import (
    adapt_friend_raw_vlm_to_request,
)

ADAPTED_AT = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def _raw(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "arac_sinifi": "sabit_kanat",
        "tehdit_seviyesi": "YUKSEK",
        "tahmini_hedef_tipi": None,
        "ulke_orjini": "ABD",
        "hedef_modeli": None,
        "gorsel_analiz": "Ham görsel hipotez",
    }
    payload.update(updates)
    return payload


def _adapt(**raw_updates: object):  # type: ignore[no-untyped-def]
    adapter_input = RawVLMAdapterRequest(
        raw_vlm=RawVLMOutput.model_validate(_raw(**raw_updates)),
        video_id="VIDEO_001",
        track_id="TRK_RAW_001",
        first_seen_offset_seconds=8.2,
        last_seen_offset_seconds=15.6,
        visual_confidence=0.31,
    )
    return adapt_friend_raw_vlm_to_request(
        adapter_input,
        adapted_at_utc=ADAPTED_AT,
    )


@pytest.mark.parametrize(
    ("raw_updates", "expected_class", "expected_hypothesis"),
    [
        ({"hedef_modeli": "Boeing 747"}, VisualClass.CIVILIAN_AIRCRAFT, "Boeing 747"),
        (
            {"hedef_modeli": "Airbus A320", "tahmini_hedef_tipi": "yolcu_ucagi"},
            VisualClass.CIVILIAN_AIRCRAFT,
            "Airbus A320",
        ),
        (
            {"hedef_modeli": "F-16 Fighting Falcon", "tahmini_hedef_tipi": "askeri_ucak"},
            VisualClass.FIGHTER_JET,
            "F-16-like",
        ),
        (
            {"hedef_modeli": "F-35 Lightning II", "tahmini_hedef_tipi": "askeri_ucak"},
            VisualClass.FIGHTER_JET,
            "F-35-like",
        ),
        (
            {"hedef_modeli": "F-35A Lightning II", "tahmini_hedef_tipi": "askeri_ucak"},
            VisualClass.FIGHTER_JET,
            "F-35A-like",
        ),
        (
            {"hedef_modeli": "General Dynamics F-16", "tahmini_hedef_tipi": "askeri_ucak"},
            VisualClass.FIGHTER_JET,
            "F-16-like",
        ),
        (
            {"hedef_modeli": "F-16 Fighting Falcon"},
            VisualClass.UNKNOWN_AIRCRAFT,
            "F-16-like",
        ),
        ({}, VisualClass.UNKNOWN_AIRCRAFT, "UNKNOWN_AIRCRAFT"),
        (
            {"hedef_modeli": "MQ-9 Reaper", "tahmini_hedef_tipi": "siha"},
            VisualClass.UNKNOWN_AIRCRAFT,
            "MQ-9 Reaper",
        ),
    ],
)
def test_safe_fixed_wing_classification_and_model_aliases(
    raw_updates: dict[str, object],
    expected_class: VisualClass,
    expected_hypothesis: str,
) -> None:
    visual = _adapt(**raw_updates).analyze_request.visual_evidence
    assert visual.visual_class is expected_class
    assert visual.final_visual_hypothesis == expected_hypothesis


def test_only_underscore_metadata_is_permitted_and_preserved() -> None:
    result = _adapt(
        _celiski_var=True,
        _vote_count=4,
        _inference_duration_seconds=91.2,
    )
    visual = result.analyze_request.visual_evidence
    assert result.helper_metadata == {
        "_inference_duration_seconds": 91.2,
        "_celiski_var": True,
        "_vote_count": 4,
    }
    assert visual.uncertainty_level is UncertaintyLevel.HIGH
    assert visual.human_visual_review_required is True
    assert "RAW_VLM_CONFLICT_REPORTED" in visual.uncertainty_flags
    assert visual.timing.first_seen_offset_seconds == 8.2
    assert visual.timing.last_seen_offset_seconds == 15.6
    assert visual.producer_metadata.created_at_utc == ADAPTED_AT


def test_weak_vrag_vote_share_raises_uncertainty_to_high() -> None:
    """BUG-FIX (kök neden araştırması): zayıf VRAG oy oranı da artık HIGH
    belirsizlik tetiklemeli, öncesinde sadece VLM'in kendi iç çelişkisi
    tetikliyordu."""
    result = _adapt(_vrag_oy_orani=0.5)
    visual = result.analyze_request.visual_evidence
    assert visual.uncertainty_level is UncertaintyLevel.HIGH
    assert "VRAG_VOTE_SHARE_WEAK" in visual.uncertainty_flags


def test_strong_vrag_vote_share_never_produces_low_uncertainty() -> None:
    """BUG-FIX (canlı testte bulundu): çok güçlü bir VRAG oy oranı (ör. %95)
    bile FinalVisualEvidencePackage'ın "VLM_ONLY modunda uncertainty asla LOW
    olamaz" kuralını ihlal edip 500 hatasına yol açmamalı - bu yol bağımsız
    bir retrieval doğrulaması (candidate_matches) OLMADAN çalışıyor."""
    result = _adapt(_vrag_oy_orani=0.95)
    visual = result.analyze_request.visual_evidence
    assert visual.uncertainty_level is UncertaintyLevel.MEDIUM


def test_video_gozlem_is_carried_to_upstream_audit_without_touching_decision_fields() -> None:
    """BUG-FIX (kullanıcı isteği — ikincil video-VLM'i sisteme entegre et):
    video_gozlem SADECE upstream_vlm_output'a (LLM'in Türkçe özetine ek bağlam
    için, bkz. evidence_builder._render_visual_evidence) taşınmalı - kimlik/
    tehdit/risk alanlarını (arac_sinifi, final_visual_hypothesis, uncertainty_
    level) hiç etkilememeli."""
    result = _adapt(
        hedef_modeli="Boeing 747",
        video_gozlem="hareket: düz uçuş, ayırt edici özellik: dört motorlu",
    )
    visual = result.analyze_request.visual_evidence
    assert visual.upstream_vlm_output.video_gozlem == "hareket: düz uçuş, ayırt edici özellik: dört motorlu"
    assert visual.final_visual_hypothesis == "Boeing 747"
    assert visual.uncertainty_level is UncertaintyLevel.MEDIUM


def test_missing_video_gozlem_defaults_to_none() -> None:
    result = _adapt(hedef_modeli="Boeing 747")
    assert result.analyze_request.visual_evidence.upstream_vlm_output.video_gozlem is None


def test_normal_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown raw VLM field"):
        RawVLMOutput.model_validate(_raw(hedef_modelli="F-16"))


def test_threat_origin_and_vote_are_audit_hypotheses_only() -> None:
    result = _adapt(_vote_count=3)
    metadata = result.analyze_request.request_metadata
    assert metadata is not None
    assert metadata["upstream_visual_threat_hypothesis"] == "YUKSEK"
    assert metadata["visual_origin_hypothesis"] == "ABD"
    assert metadata["raw_vlm_helper_metadata"] == {"_vote_count": 3}
    assert result.analyze_request.visual_evidence.upstream_vlm_output.tehdit_seviyesi == "YUKSEK"
    assert result.analyze_request.visual_evidence.upstream_vlm_output.ulke_orjini == "ABD"


def test_visual_confidence_is_explicit_and_not_invented_from_raw_payload() -> None:
    result = _adapt()
    visual = result.analyze_request.visual_evidence
    assert visual.visual_confidence == 0.31
    assert visual.upstream_vlm_output.guven_skoru == 31

    incomplete = {
        "raw_vlm": _raw(),
        "video_id": "VIDEO_001",
        "track_id": "TRK_RAW_001",
        "first_seen_offset_seconds": 8.2,
        "last_seen_offset_seconds": 15.6,
    }
    with pytest.raises(ValidationError):
        RawVLMAdapterRequest.model_validate(incomplete)

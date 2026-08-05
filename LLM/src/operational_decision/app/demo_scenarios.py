"""Deterministic DEMO_MOCK scenario catalog and analyze-request builder."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from operational_decision.contracts.common import (
    RiskLevel,
    StrictContract,
    VerificationStatus,
)
from operational_decision.contracts.raw_vlm import RawVLMAdapterRequest, RawVLMOutput
from operational_decision.contracts.request import AnalyzeEventRequest
from operational_decision.input.upstream_vlm_adapter import adapt_friend_raw_vlm_to_request


class DemoScenarioDefinition(StrictContract):
    """Seed-owned metadata for one binding demo scenario."""

    scenario_id: str = Field(pattern=r"^SCN-(0[1-9]|1[0-9]|2[0-3])$")
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=1000)
    expected_verification_status: VerificationStatus
    expected_risk_level: RiskLevel
    source_type: Literal["DEMO_MOCK"]


def build_demo_request(
    project_root: Path,
    scenario_id: str,
    *,
    released: bool = True,
) -> AnalyzeEventRequest:
    """Build a strict canonical request from the shared request fixture."""
    match = re.fullmatch(r"SCN-(0[1-9]|1[0-9]|2[0-3])", scenario_id)
    if match is None:
        raise ValueError("scenario_id must be SCN-01 through SCN-23")
    scenario_number = int(match.group(1))
    payload = json.loads(
        (project_root / "examples/analyze_event_request.json").read_text(encoding="utf-8")
    )
    payload["video_id"] = f"VIDEO_{scenario_number:03d}"
    payload["gpu_handoff"]["gpu_release_status"] = "RELEASED" if released else "PENDING"
    visual = payload["visual_evidence"]
    visual["track_id"] = f"TRK_{scenario_number:03d}"
    if scenario_number == 6:
        visual["visual_class"] = "UNKNOWN_AIRCRAFT"
        visual["final_visual_hypothesis"] = "UNRESOLVED-PLATFORM"
        visual["uncertainty_level"] = "HIGH"
    if scenario_number == 8:
        visual.update(
            {
                "evidence_source_mode": "FUSED",
                "visual_class": "NON_AIRCRAFT",
                "final_visual_hypothesis": None,
                "candidate_matches": [{"rank": 1, "candidate_name": "NON_AIRCRAFT", "score": 0.95}],
                "visual_evidence_status": "SUPPORTED",
                "visual_confidence": 0.95,
                "confidence_origin": "UPSTREAM_FUSION",
                "uncertainty_level": "LOW",
                "human_visual_review_required": False,
            }
        )
    if scenario_number == 13:
        visual.update(
            {
                "evidence_source_mode": "FUSED",
                "visual_class": "CIVILIAN_AIRCRAFT",
                "final_visual_hypothesis": "Boeing 747",
                "candidate_matches": [{"rank": 1, "candidate_name": "Boeing 747", "score": 0.85}],
                "visual_evidence_status": "PARTIALLY_SUPPORTED",
                "visual_confidence": 0.85,
                "confidence_origin": "UPSTREAM_FUSION",
                "uncertainty_level": "MEDIUM",
                "human_visual_review_required": False,
            }
        )
        visual["upstream_vlm_output"].update(
            {
                "arac_sinifi": "SIVIL_UCAK",
                "tehdit_seviyesi": "BILINMIYOR",
                "tahmini_hedef_tipi": "YOLCU_KARGO_UCAGI",
                "ulke_orjini": "Bilinmiyor",
                "hedef_modeli": "Boeing 747",
                "gorsel_analiz": (
                    "Görüntüde dört motorlu geniş gövdeli yolcu veya kargo "
                    "uçağı hipotezi bulunmaktadır."
                ),
                "guven_skoru": 85,
            }
        )
    if scenario_number == 23:
        visual.update(
            {
                "evidence_source_mode": "FUSED",
                "visual_class": "CIVILIAN_AIRCRAFT",
                "final_visual_hypothesis": "Boeing 747",
                "candidate_matches": [{"rank": 1, "candidate_name": "Boeing 747", "score": 0.85}],
                "visual_evidence_status": "PARTIALLY_SUPPORTED",
                "visual_confidence": 0.85,
                "confidence_origin": "UPSTREAM_FUSION",
                "uncertainty_level": "MEDIUM",
                "human_visual_review_required": False,
            }
        )
        visual["upstream_vlm_output"].update(
            {
                "arac_sinifi": "SABIT_KANAT",
                "tehdit_seviyesi": "DUSUK",
                "tahmini_hedef_tipi": "YOLCU_UCAGI",
                "ulke_orjini": "Bilinmiyor",
                "hedef_modeli": "Boeing 747",
                "gorsel_analiz": (
                    "Görüntüde dört motorlu geniş gövdeli bir sivil yolcu uçağı silueti "
                    "görülmektedir; ön gövdedeki karakteristik kambur yapı ve dört motor "
                    "Boeing 747 modelini güçlü biçimde işaret etmektedir. Net ülke veya "
                    "operatör işareti okunamamaktadır."
                ),
                "guven_skoru": 85,
            }
        )
    if scenario_number == 14:
        visual.update(
            {
                "visual_class": "UCAV",
                "final_visual_hypothesis": "Bayraktar TB2",
                "candidate_matches": [],
                "visual_evidence_status": "PARTIALLY_SUPPORTED",
                "visual_confidence": 0.85,
                "uncertainty_level": "MEDIUM",
                "human_visual_review_required": True,
            }
        )
        visual["upstream_vlm_output"].update(
            {
                "arac_sinifi": "SIHA",
                "tehdit_seviyesi": "BILINMIYOR",
                "tahmini_hedef_tipi": "SIHA",
                "ulke_orjini": "TR",
                "hedef_modeli": "Bayraktar TB2",
                "gorsel_analiz": "Görüntüde Bayraktar TB2 SİHA model hipotezi bulunmaktadır.",
                "guven_skoru": 85,
            }
        )
    if scenario_number == 15:
        visual.update(
            {
                "visual_class": "UCAV",
                "final_visual_hypothesis": "Bayraktar AKINCI",
                "candidate_matches": [],
                "visual_evidence_status": "PARTIALLY_SUPPORTED",
                "visual_confidence": 0.85,
                "uncertainty_level": "MEDIUM",
                "human_visual_review_required": True,
            }
        )
        visual["upstream_vlm_output"].update(
            {
                "arac_sinifi": "AGIR_SINIF_SIHA",
                "tehdit_seviyesi": "BILINMIYOR",
                "tahmini_hedef_tipi": "AGIR_SINIF_SIHA",
                "ulke_orjini": "TR",
                "hedef_modeli": "Bayraktar AKINCI",
                "gorsel_analiz": (
                    "Görüntüde Bayraktar AKINCI Ağır sınıf SİHA model hipotezi bulunmaktadır."
                ),
                "guven_skoru": 85,
            }
        )
    if scenario_number == 16:
        visual.update(
            {
                "visual_class": "UAV",
                "final_visual_hypothesis": "TUSAŞ ANKA",
                "candidate_matches": [],
                "visual_evidence_status": "PARTIALLY_SUPPORTED",
                "visual_confidence": 0.85,
                "uncertainty_level": "MEDIUM",
                "human_visual_review_required": True,
            }
        )
        visual["upstream_vlm_output"].update(
            {
                "arac_sinifi": "IHA",
                "tehdit_seviyesi": "BILINMIYOR",
                "tahmini_hedef_tipi": "MALE_IHA",
                "ulke_orjini": "TR",
                "hedef_modeli": "TUSAŞ ANKA",
                "gorsel_analiz": (
                    "Görüntüde TUSAŞ ANKA Orta irtifa uzun havada kalışlı İHA "
                    "model hipotezi bulunmaktadır."
                ),
                "guven_skoru": 85,
            }
        )
    if scenario_number == 17:
        visual.update(
            {
                "visual_class": "FIGHTER_JET",
                "final_visual_hypothesis": "F-35A Lightning II",
                "candidate_matches": [],
                "visual_evidence_status": "PARTIALLY_SUPPORTED",
                "visual_confidence": 0.85,
                "uncertainty_level": "MEDIUM",
                "human_visual_review_required": True,
            }
        )
        visual["upstream_vlm_output"].update(
            {
                "arac_sinifi": "SAVAS_UCAGI",
                "tehdit_seviyesi": "BILINMIYOR",
                "tahmini_hedef_tipi": "SAVAS_UCAGI",
                "ulke_orjini": "US",
                "hedef_modeli": "F-35A Lightning II",
                "gorsel_analiz": "Görüntüde F-35A Lightning II savaş uçağı model hipotezi vardır.",
                "guven_skoru": 85,
            }
        )
    if scenario_number == 18:
        raw_payload = json.loads(
            (project_root / "examples/raw_vlm_mq9_reaper.json").read_text(encoding="utf-8")
        )
        adapted = adapt_friend_raw_vlm_to_request(
            RawVLMAdapterRequest(
                raw_vlm=RawVLMOutput.model_validate(raw_payload),
                video_id="VIDEO_018",
                track_id="TRK_018",
                first_seen_offset_seconds=8.2,
                last_seen_offset_seconds=15.6,
                visual_confidence=0.85,
            ),
            adapted_at_utc=datetime(2026, 8, 11, 4, 20, tzinfo=UTC),
        )
        payload = adapted.analyze_request.model_dump(mode="json")
    if scenario_number in {19, 20, 21, 22}:
        new_visuals = {
            19: (
                "UCAV",
                "Bayraktar AKINCI",
                "AGIR_SINIF_SIHA",
                "AGIR_SINIF_SIHA",
                "Bayraktar AKINCI için kontrollü görsel model hipotezi.",
            ),
            20: (
                "UCAV",
                "Bayraktar TB2",
                "SIHA",
                "SIHA",
                "Bayraktar TB2 için kontrollü görsel model hipotezi.",
            ),
            21: (
                "FIGHTER_JET",
                "F-16",
                "SAVAS_UCAGI",
                "MUHARIP_JET",
                "F-16 için kontrollü görsel model hipotezi.",
            ),
            22: (
                "UAV",
                "TUSAŞ ANKA",
                "IHA",
                "MALE_IHA",
                "TUSAŞ ANKA için kontrollü görsel model hipotezi.",
            ),
        }
        visual_class, model, upstream_class, target_type, analysis = new_visuals[scenario_number]
        visual.update(
            {
                "visual_class": visual_class,
                "final_visual_hypothesis": model,
                "candidate_matches": [],
                "visual_evidence_status": "PARTIALLY_SUPPORTED",
                "visual_confidence": 0.85,
                "uncertainty_level": "MEDIUM",
                "human_visual_review_required": True,
            }
        )
        visual["upstream_vlm_output"].update(
            {
                "arac_sinifi": upstream_class,
                "tehdit_seviyesi": "BILINMIYOR",
                "tahmini_hedef_tipi": target_type,
                "ulke_orjini": "TR",
                "hedef_modeli": model,
                "gorsel_analiz": analysis,
                "guven_skoru": 85,
            }
        )
    payload["request_metadata"] = {
        **(payload.get("request_metadata") or {}),
        "scenario_id": scenario_id,
        "source_type": "DEMO_MOCK",
        "provenance": "data/seeds/demo_scenarios.json",
    }
    return AnalyzeEventRequest.model_validate_json(
        json.dumps(payload, ensure_ascii=False), strict=True
    )


def load_demo_scenario_definitions(path: Path) -> list[DemoScenarioDefinition]:
    """Load and strictly validate the ordered seed catalog."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("scenario catalog must be a list")
    definitions = [
        DemoScenarioDefinition.model_validate_json(
            json.dumps(item, ensure_ascii=False), strict=True
        )
        for item in payload
    ]
    expected_ids = [f"SCN-{number:02d}" for number in range(1, 24)]
    if [item.scenario_id for item in definitions] != expected_ids:
        raise ValueError("scenario catalog must contain ordered SCN-01 through SCN-23")
    return definitions

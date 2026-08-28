"""Safe raw VLM payload adapter tests."""
# ruff: noqa: D103

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from operational_decision.contracts.common import VisualClass
from operational_decision.contracts.visual import ProducerMetadata, UpstreamTrackContext
from operational_decision.input.raw_vlm_adapter import adapt_raw_vlm_payload
from operational_decision.input.upstream_vlm_adapter import map_upstream_vlm_to_canonical


def _payload(vehicle_class: str, **updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "upstream-vlm/1.0",
        "arac_sinifi": vehicle_class,
        "tehdit_seviyesi": None,
        "tahmini_hedef_tipi": None,
        "ulke_orjini": None,
        "hedef_modeli": None,
        "gidis_yeri": None,
        "gorsel_analiz": "Genel görsel gözlem",
        "guven_skoru": 70,
    }
    payload.update(updates)
    return payload


def test_only_underscore_prefixed_helper_metadata_is_removed() -> None:
    adapted = adapt_raw_vlm_payload(
        _payload("sabit_kanat", _latency_ms=12, _producer={"name": "raw"})
    )
    assert adapted.arac_sinifi == "BILINMEYEN_HAVA_ARACI"
    assert adapted.model_dump().keys() == {
        "schema_version",
        "arac_sinifi",
        "tehdit_seviyesi",
        "tahmini_hedef_tipi",
        "ulke_orjini",
        "hedef_modeli",
        "gidis_yeri",
        "gorsel_analiz",
        "guven_skoru",
        "video_gozlem",
    }


def test_normal_unknown_field_remains_a_validation_error() -> None:
    with pytest.raises(ValidationError):
        adapt_raw_vlm_payload(_payload("sabit_kanat", producer="unexpected"))


@pytest.mark.parametrize(
    ("vehicle_class", "updates", "expected"),
    [
        ("sabit_kanat", {}, "BILINMEYEN_HAVA_ARACI"),
        (
            "sabit_kanat",
            {"hedef_modeli": "F-16", "tahmini_hedef_tipi": "askeri_ucak"},
            "SAVAS_UCAGI",
        ),
        ("sabit_kanat", {"tahmini_hedef_tipi": "muharip jet"}, "BILINMEYEN_HAVA_ARACI"),
        ("döner_kanat", {}, "BILINMEYEN_HAVA_ARACI"),
        ("döner_kanat", {"tahmini_hedef_tipi": "helikopter"}, "HELIKOPTER"),
    ],
)
def test_broad_raw_classes_are_mapped_conservatively(
    vehicle_class: str, updates: dict[str, object], expected: str
) -> None:
    assert adapt_raw_vlm_payload(_payload(vehicle_class, **updates)).arac_sinifi == expected


def test_broad_fixed_wing_does_not_overclaim_fighter_identity() -> None:
    raw = adapt_raw_vlm_payload(_payload("sabit_kanat"))
    canonical = map_upstream_vlm_to_canonical(
        raw_vlm=raw,
        track_context=UpstreamTrackContext(
            track_id="track-1",
            first_seen_offset_seconds=0,
            last_seen_offset_seconds=1,
            track_duration_seconds=1,
            track_stability=0.8,
            detection_count=2,
            average_detection_confidence=0.7,
        ),
        producer_metadata=ProducerMetadata.model_validate(
            {
                "visual_pipeline_version": "test",
                "vlm_model": "test",
                "created_at_utc": datetime(2026, 1, 1, tzinfo=UTC),
            }
        ),
    )
    assert canonical.visual_class is VisualClass.UNKNOWN_AIRCRAFT
    assert canonical.final_visual_hypothesis == "UNKNOWN_AIRCRAFT"

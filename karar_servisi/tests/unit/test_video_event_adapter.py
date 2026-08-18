"""Future-compatible video event projection tests."""
# ruff: noqa: D103

import json
from pathlib import Path

from pydantic import TypeAdapter

from apps.demo_ui.components import VIDEO_EVENTS_PENDING_MESSAGE, video_event_rows
from operational_decision.app.config import AppSettings
from operational_decision.contracts.raw_vlm import RawVLMOutput
from operational_decision.contracts.video_events import RawVideoEvent
from operational_decision.input.raw_vlm_assessment import assess_raw_vlm
from operational_decision.input.video_event_adapter import map_video_event_projection

FIXTURE = Path("tests/fixtures/video_events/real_timestamp_events.json")


def _boeing_raw(**updates: object) -> RawVLMOutput:
    payload: dict[str, object] = {
        "arac_sinifi": "sabit_kanat",
        "tehdit_seviyesi": "dusuk",
        "tahmini_hedef_tipi": "sivil_ucak",
        "ulke_orjini": "Bilinmiyor",
        "hedef_modeli": "Boeing 747",
        "gorsel_analiz": "Görüntü Boeing 747 platform hipotezini destekliyor.",
    }
    payload.update(updates)
    return RawVLMOutput.model_validate(payload)


def test_raw_boeing_without_video_timing_never_gets_a_synthetic_event() -> None:
    settings = AppSettings()
    result = assess_raw_vlm(
        _boeing_raw(),
        platform_registry_path=settings.platform_registry_path,
        platform_aliases_path=settings.platform_aliases_path,
        inventory_path=settings.turkey_inventory_registry_path,
    )

    assert result.timestamped_events == []
    assert result.timestamps_available is False
    assert result.event_extraction_status == "PENDING_VIDEO_EVENT_INTEGRATION"
    assert result.untimestamped_visual_assessment is not None
    assert result.untimestamped_visual_assessment.model_dump() == {
        "type": "VISUAL_PLATFORM_ASSESSMENT",
        "timestamp": None,
        "source": "RAW_VLM",
        "critical": False,
        "description_tr": "Görüntü Boeing 747 platform hipotezini destekliyor.",
    }
    assert VIDEO_EVENTS_PENDING_MESSAGE == (
        "Zaman damgalı olaylar, video olay çıkarım modülü entegre edildiğinde gösterilecektir."
    )


def test_real_video_event_timestamps_are_preserved_and_sorted_by_first_seen() -> None:
    events = TypeAdapter(list[RawVideoEvent]).validate_json(FIXTURE.read_text(encoding="utf-8"))

    projection = map_video_event_projection(events)
    dumped = projection.model_dump(mode="json")

    assert projection.timestamps_available is True
    assert projection.event_extraction_status == "AVAILABLE"
    assert [item["event_id"] for item in dumped["timestamped_events"]] == [
        "EVT-001",
        "EVT-002",
    ]
    assert dumped["timestamped_events"][0]["first_seen"] == "00:03.125"
    assert dumped["timestamped_events"][0]["last_seen"] == "00:08.750"
    assert dumped["timestamped_events"][1]["first_seen"] == "00:12.480"
    assert dumped["timestamped_events"][1]["last_seen"] == "00:15.900"
    assert dumped["timestamped_events"][1]["critical_moment"] is True
    assert video_event_rows(dumped)[1]["critical_moment"] is True


def test_notam_validity_dates_cannot_become_video_event_timestamps() -> None:
    notam_record = {
        "valid_from_utc": "2026-08-11T09:00:00.000Z",
        "valid_until_utc": "2026-08-11T10:00:00.000Z",
    }

    projection = map_video_event_projection(
        None,
        visual_assessment_tr=json.dumps(notam_record),
    )

    assert projection.timestamped_events == []
    assert projection.timestamps_available is False
    assert projection.event_extraction_status == "PENDING_VIDEO_EVENT_INTEGRATION"

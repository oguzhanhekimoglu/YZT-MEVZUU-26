"""Runtime mode boundaries for demo routing and production context."""
# ruff: noqa: D103

from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest

from apps.demo_ui.app import main
from apps.demo_ui.raw_vlm_context_router import (
    resolve_raw_vlm_runtime_context,
    resolve_raw_vlm_visual_confidence,
)
from operational_decision.api.main import create_app
from operational_decision.app import bootstrap
from operational_decision.app.config import AppSettings
from operational_decision.app.container import ApplicationContainer
from operational_decision.contracts.raw_vlm import RawVLMAdapterRequest
from operational_decision.input.upstream_vlm_adapter import adapt_friend_raw_vlm_to_request
from operational_decision.operational.database import OperationalDatabase


def _raw_vlm() -> dict[str, object]:
    return {
        "arac_sinifi": "sabit_kanat",
        "tehdit_seviyesi": "dusuk",
        "tahmini_hedef_tipi": "askeri_ucak",
        "ulke_orjini": "Bilinmiyor",
        "hedef_modeli": "F-35A Lightning II",
        "gorsel_analiz": "F-35A platform hipotezi.",
    }


def test_demo_mode_preserves_platform_context_route() -> None:
    context, is_fallback = resolve_raw_vlm_runtime_context(
        runtime_mode="DEMO",
        platform_id="PLT_F35A",
        demo_track_id="TRK_DEMO",
    )
    assert context == {
        "video_id": "VIDEO_017",
        "track_id": "TRK_DEMO",
        "first_seen_offset_seconds": 0.0,
        "last_seen_offset_seconds": 1.0,
    }
    assert is_fallback is False


def test_production_mode_ignores_platform_route_and_preserves_upstream_timing() -> None:
    context, is_fallback = resolve_raw_vlm_runtime_context(
        runtime_mode="PRODUCTION",
        platform_id="PLT_F35A",
        upstream_video_id="VIDEO_REAL_900",
        upstream_track_id="TRACK_REAL_42",
        first_seen_offset_seconds=12.5,
        last_seen_offset_seconds=19.75,
    )
    assert context == {
        "video_id": "VIDEO_REAL_900",
        "track_id": "TRACK_REAL_42",
        "first_seen_offset_seconds": 12.5,
        "last_seen_offset_seconds": 19.75,
    }
    assert is_fallback is False
    adapted = adapt_friend_raw_vlm_to_request(
        RawVLMAdapterRequest.model_validate(
            {"raw_vlm": _raw_vlm(), **context, "visual_confidence": 0.8}
        )
    )
    timing = adapted.analyze_request.visual_evidence.timing
    assert timing.first_seen_offset_seconds == 12.5
    assert timing.last_seen_offset_seconds == 19.75


def test_production_mode_rejects_missing_context_without_synthetic_timing() -> None:
    with pytest.raises(ValueError, match="CONTEXT_MISSING"):
        resolve_raw_vlm_runtime_context(
            runtime_mode="PRODUCTION",
            platform_id="PLT_F35A",
            upstream_video_id="VIDEO_REAL_900",
            upstream_track_id="TRACK_REAL_42",
        )


@pytest.mark.asyncio
async def test_production_bootstrap_does_not_load_demo_mock_seeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seed = AsyncMock()
    monkeypatch.setattr(bootstrap, "seed_operational_database", seed)
    database = cast(OperationalDatabase, object())
    await bootstrap._seed_runtime_operational_data(
        database,
        AppSettings(
            runtime_mode="PRODUCTION",
            operational_db_path=tmp_path / "production-operational.db",
            event_db_path=tmp_path / "production-events.db",
            seed_directory=tmp_path,
        ),
    )
    seed.assert_not_awaited()
    await bootstrap._seed_runtime_operational_data(
        database,
        AppSettings(runtime_mode="DEMO", seed_directory=tmp_path),
    )
    seed.assert_awaited_once_with(database, tmp_path)

def _production_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPERATIONAL_DECISION_RUNTIME_MODE", "PRODUCTION")
    monkeypatch.setenv(
        "OPERATIONAL_DECISION_OPERATIONAL_DB_PATH",
        str(tmp_path / "production-operational.db"),
    )
    monkeypatch.setenv(
        "OPERATIONAL_DECISION_EVENT_DB_PATH",
        str(tmp_path / "production-events.db"),
    )


def test_production_requires_explicit_isolated_database_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="PRODUCTION_OPERATIONAL_DB_PATH_REQUIRED"):
        AppSettings(runtime_mode="PRODUCTION")
    settings = AppSettings(
        runtime_mode="PRODUCTION",
        operational_db_path=tmp_path / "operational.db",
        event_db_path=tmp_path / "events.db",
    )
    assert settings.operational_db_path != settings.event_db_path


@pytest.mark.asyncio
async def test_production_rejects_database_containing_demo_mock(tmp_path: Path) -> None:
    database = OperationalDatabase(tmp_path / "contaminated.db")
    await database.initialize()
    await bootstrap.seed_operational_database(database, Path("data/seeds"))
    with pytest.raises(RuntimeError, match="PRODUCTION_DATABASE_CONTAINS_DEMO_MOCK"):
        await bootstrap._assert_no_demo_mock_operational_data(database)


def test_production_visual_confidence_is_required_and_never_invented() -> None:
    with pytest.raises(ValueError, match="VISUAL_CONFIDENCE_MISSING"):
        resolve_raw_vlm_visual_confidence(
            runtime_mode="PRODUCTION",
            upstream_visual_confidence=None,
        )
    assert resolve_raw_vlm_visual_confidence(
        runtime_mode="PRODUCTION", upstream_visual_confidence=0.73
    ) == 0.73
    assert resolve_raw_vlm_visual_confidence(
        runtime_mode="DEMO", upstream_visual_confidence=None
    ) == 0.50


@pytest.mark.asyncio
async def test_production_hides_demo_endpoint_and_raw_assessment_uses_no_demo_inventory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _production_environment(monkeypatch, tmp_path)
    container = ApplicationContainer(
        orchestrator=cast(Any, None),
        event_service=cast(Any, None),
        health_service=cast(Any, None),
        scenario_path=Path("data/seeds/demo_scenarios.json"),
        runtime_mode="PRODUCTION",
    )
    app = create_app(container)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        demo = await client.get("/api/v1/demo/scenarios")
        assessment = await client.post("/api/v1/analyze/raw-vlm", json=_raw_vlm())
    assert demo.status_code == 404
    assert demo.json()["detail"] == "DEMO_ENDPOINT_DISABLED"
    assert assessment.status_code == 200
    assert assessment.json()["platform_id"] == "PLT_F35A"
    assert assessment.json()["inventory_status"] == "UNKNOWN"
    assert assessment.json()["inventory_operator_name"] is None


def test_production_ui_guards_developer_demo_section() -> None:
    import inspect

    source = inspect.getsource(main)
    guard = source.index('if runtime_mode == "DEMO":', source.index("_analysis_result(client)"))
    developer = source.index('st.expander("Geliştirici / Demo Modu"')
    assert guard < developer

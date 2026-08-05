"""UI regressions for automated platform-routed Ham VLM context and safety."""
# ruff: noqa: D103

import inspect
import json
from pathlib import Path

from apps.demo_ui.app import (
    _raw_vlm_input,
    _scenario_input,
    main,
)
from apps.demo_ui.raw_vlm_context_router import (
    load_raw_vlm_context_routes,
    raw_vlm_fallback_video_id,
    validate_route_mapping,
)
from operational_decision.input.raw_vlm_adapter import normalize_raw_model_hypothesis

ROOT = Path(__file__).resolve().parents[2]
VIDEO_CONTEXTS_PATH = ROOT / "data/seeds/video_contexts.json"


def test_f35_variant_is_explicit_and_family_is_not_promoted() -> None:
    assert normalize_raw_model_hypothesis("F-35A Lightning II") == "F-35A-like"
    assert normalize_raw_model_hypothesis("F-35 Lightning II") == "F-35-like"


def test_raw_vlm_route_mapping_references_only_existing_active_contexts() -> None:
    errors = validate_route_mapping()
    assert errors == [], errors

    routes = load_raw_vlm_context_routes()
    fallback = raw_vlm_fallback_video_id()
    all_video_ids = list(routes.values()) + [fallback]

    contexts = json.loads(VIDEO_CONTEXTS_PATH.read_text(encoding="utf-8"))
    active_ids = {
        item["video_id"]
        for item in contexts
        if isinstance(item, dict) and item.get("status") == "ACTIVE"
    }
    for video_id in all_video_ids:
        assert video_id in active_ids, f"{video_id} is not an ACTIVE context"

    assert len(set(all_video_ids)) == len(all_video_ids) or len(routes) >= len(set(routes.values()))


def test_raw_vlm_ui_uses_automatic_platform_routing_not_manual_context() -> None:
    source = inspect.getsource(_raw_vlm_input)

    assert "Video / Operasyonel Bağlam" not in source
    assert "selected_context is None" not in source
    assert "context_options[selected_context]" not in source
    assert "resolve_raw_vlm_runtime_context" in source
    assert "assess" in source.lower() or "analyze_raw_vlm_only" in source
    assert "adapt_raw_vlm(adapter_payload)" in source
    assert "client.analyze(canonical, response_format)" in source


def test_output_format_choices_are_explicit_in_demo_and_raw_vlm() -> None:
    raw_source = inspect.getsource(_raw_vlm_input)
    scenario_source = inspect.getsource(_scenario_input)
    main_source = inspect.getsource(main)

    assert "response_format" not in inspect.signature(_raw_vlm_input).parameters
    assert "TEKNOFEST Şartname" in raw_source
    assert "client.analyze(canonical, response_format)" in raw_source
    assert "Hazır demo çıktı görünümü" in scenario_source
    assert "TEKNOFEST kısa format" in scenario_source
    assert "client.analyze(payload, response_format)" in scenario_source
    assert "Çıktı formatı" not in main_source


def test_origin_assessment_and_operational_pipeline_run_together() -> None:
    source = inspect.getsource(_raw_vlm_input)

    assert "analyze_raw_vlm_only(raw_vlm)" in source
    assert "adapt_raw_vlm(adapter_payload)" in source
    assert "client.analyze(canonical, response_format)" in source
    assert "Uçağın kesin ülke orijini" in source or "ülke" in source
    assert "Platform Registry kaydından alınır" in source


def test_scenarios_are_in_developer_mode_section() -> None:
    source = inspect.getsource(main)

    assert "Geliştirici / Demo Modu" in source
    assert "_scenario_input(client)" in source
    assert "st.expander" in source


def test_no_context_selectbox_in_raw_vlm_ui() -> None:
    source = inspect.getsource(_raw_vlm_input)

    assert "st.selectbox" not in source
    assert "raw_operational_context" not in source

def test_registry_platform_catalog_is_collapsible() -> None:
    source = inspect.getsource(_raw_vlm_input)

    assert 'st.expander("Registry platformları", expanded=False)' in source

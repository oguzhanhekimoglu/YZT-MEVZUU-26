"""Streamlit startup and visible-input regressions."""
# ruff: noqa: D103

from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]


def test_demo_ui_starts_without_backend() -> None:
    app = AppTest.from_file(ROOT / "apps/demo_ui/app.py")
    app.run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "Operational Decision V1 — Manuel Test Arayüzü"


def test_mq9_raw_vlm_example_is_visible() -> None:
    app = AppTest.from_file(ROOT / "apps/demo_ui/app.py")
    app.run(timeout=30)
    assert any("MQ-9 Reaper" in item.value for item in app.text_area)


def test_canonical_json_input_tab_is_not_exposed() -> None:
    app = AppTest.from_file(ROOT / "apps/demo_ui/app.py")
    app.run(timeout=30)

    # First text area in main view must be "Ham VLM JSON", not "Request JSON"
    assert app.text_area[0].label == "Ham VLM JSON"
    assert any(item.label == "Ham VLM JSON" for item in app.text_area)
    assert any(expander.label == "Geliştirici / Demo Modu" for expander in app.expander)
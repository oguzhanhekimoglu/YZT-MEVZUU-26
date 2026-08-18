"""Streamlit manual test client for the existing Operational Decision API."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from apps.demo_ui.api_client import (
    APIResult,
    DemoAPIClient,
    parse_json_text,
    run_demo_scenarios,
    scenario_request_payload,
)
from apps.demo_ui.components import (
    render_health,
    render_http_outcome,
    render_raw_vlm_analysis,
    render_sources,
    render_teknofest_spec,
    render_trace,
    render_video_events,
    response_output,
    rows_to_csv,
    shown,
)
from apps.demo_ui.raw_vlm_context_router import (
    resolve_raw_vlm_runtime_context,
    resolve_raw_vlm_visual_confidence,
)
from operational_decision.app.config import AppSettings

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_REQUEST = ROOT / "examples/analyze_event_request.json"
RAW_VLM_EXAMPLE_PATH = ROOT / "examples/raw_vlm_mq9_reaper.json"
RAW_VLM_EXAMPLE = json.loads(RAW_VLM_EXAMPLE_PATH.read_text(encoding="utf-8"))
PLATFORM_REGISTRY_PATH = ROOT / "data/platforms/platform_registry.json"
TURKEY_INVENTORY_PATH = ROOT / "data/inventory/turkey_inventory.json"


def _active_platform_catalog(*, include_demo_inventory: bool = True) -> list[dict[str, str]]:
    """Build the active platform catalog from Registry and Turkey Inventory."""
    registry = json.loads(PLATFORM_REGISTRY_PATH.read_text(encoding="utf-8"))
    inventory = (
        json.loads(TURKEY_INVENTORY_PATH.read_text(encoding="utf-8"))
        if include_demo_inventory
        else {"records": []}
    )
    platforms = registry.get("platforms", [])
    inventory_records = inventory.get("records", [])
    if not isinstance(platforms, list) or not isinstance(inventory_records, list):
        return []
    inventory_ids = {
        item.get("platform_id")
        for item in inventory_records
        if isinstance(item, dict) and item.get("active") is True
    }
    user_type_labels = {
        "UAV": "\u0130HA",
        "UCAV": "S\u0130HA",
        "HELICOPTER": "Helikopter",
        "TRANSPORT_AIRCRAFT": "Nakliye u\u00e7a\u011f\u0131",
        "FIGHTER_JET": "Sava\u015f u\u00e7a\u011f\u0131",
        "CIVILIAN_AIRCRAFT": "Sivil u\u00e7ak",
        "MICRO_DRONE": "Mini \u0130HA",
    }
    catalog: list[dict[str, str]] = []
    for item in platforms:
        if not isinstance(item, dict) or item.get("active") is not True:
            continue
        platform_id = item.get("platform_id")
        name = item.get("canonical_name")
        category = item.get("category")
        aliases = item.get("aliases", [])
        if not all(isinstance(value, str) for value in (platform_id, name, category)):
            continue
        usable_aliases = [alias for alias in aliases if isinstance(alias, str)]
        catalog.append(
            {
                "platform_id": platform_id,
                "canonical_name": name,
                "user_type": user_type_labels.get(category, category.replace("_", " ").title()),
                "category": category,
                "inventory": (
                    "Envanter \u0130\u00e7i"
                    if platform_id in inventory_ids
                    else "Envanter D\u0131\u015f\u0131"
                ),
                "aliases": ", ".join(usable_aliases),
            }
        )
    return catalog


def _initialize_state() -> None:
    defaults: dict[str, Any] = {
        "health_body": None,
        "rag_body": None,
        "scenarios": [],
        "manual_json": "{}",
        "raw_vlm_json": json.dumps(RAW_VLM_EXAMPLE, ensure_ascii=False, indent=2),
        "raw_adapter_result": None,
        "raw_adapter_request": None,
        "raw_vlm_submission": None,
        "raw_vlm_assessment": None,
        "request_payload": None,
        "analyze_result": None,
        "analysis_response_format": "canonical",
        "event_body": None,
        "trace_body": None,
        "event_id": None,
        "pending_payload": None,
        "scenario_smoke_rows": [],
        "uploaded_signature": None,
        "production_video_id": "",
        "production_track_id": "",
        "production_first_seen": "",
        "production_last_seen": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _body_dict(result: APIResult | None) -> dict[str, Any]:
    if result is None or not isinstance(result.body, dict):
        return {}
    return result.body


def _store_analysis(
    result: APIResult,
    payload: Any,
    response_format: Literal["canonical", "teknofest_spec"],
) -> None:
    st.session_state.analyze_result = result
    st.session_state.request_payload = payload
    st.session_state.analysis_response_format = response_format
    body = _body_dict(result)
    event_id = body.get("event_id")
    st.session_state.event_id = event_id if isinstance(event_id, str) else None
    st.session_state.pending_payload = payload if result.status_code == 202 else None
    st.session_state.event_body = None
    st.session_state.trace_body = None


def _show_api_error(result: APIResult) -> None:
    """Show user-safe Turkish transport and validation errors."""
    if result.status_code is None and result.error_code == "CONNECTION_ERROR":
        st.error("Backend API çalışmıyor. Önce uvicorn servisini başlatın.")
        return
    if result.status_code == 422:
        body = result.body if isinstance(result.body, dict) else {}
        raw_errors = body.get("validation_errors")
        errors = raw_errors if isinstance(raw_errors, list) else []
        st.error("Girdi doğrulanamadı. Aşağıdaki alanları kontrol edin:")
        if errors:
            for raw in errors:
                item = raw if isinstance(raw, dict) else {}
                st.markdown(f"- {shown(item.get('message'))}")
        else:
            st.markdown("- Gönderilen JSON canonical sözleşmeyle uyumlu değil.")
        return
    if result.error_message:
        st.error(result.error_message)
    with st.expander("Geliştirici ayrıntısı", expanded=False):
        st.write("error_code:", shown(result.error_code))
        st.write("latency_ms:", result.latency_ms)
        st.json(result.body if result.body is not None else {})


def _load_health(client: DemoAPIClient) -> None:
    health = client.health()
    rag = client.rag_status()
    st.session_state.health_body = health.body
    st.session_state.rag_body = rag.body
    if health.status_code is None:
        _show_api_error(health)
    if rag.status_code is None:
        _show_api_error(rag)


def _load_scenarios(client: DemoAPIClient) -> None:
    result = client.scenarios()
    if result.ok and isinstance(result.body, list):
        st.session_state.scenarios = [item for item in result.body if isinstance(item, dict)]
    else:
        st.session_state.scenarios = []
        render_http_outcome(result.status_code, result.error_code, result.latency_ms)
        _show_api_error(result)


def _raw_vlm_input(client: DemoAPIClient) -> None:
    """Run raw VLM with mode-bounded operational context handling."""
    runtime_mode = AppSettings().runtime_mode
    if runtime_mode == "DEMO":
        st.info(
            "Ham VLM JSON platform ve \u00fclke hipotezini sa\u011flar. DEMO modunda sistem "
            "platformu \u00e7\u00f6zer ve yaln\u0131z DEMO_MOCK operasyon context'ine "
            "y\u00f6nlendirir."
            "Platform Registry kaydından alınır."
        )
    else:
        st.info(
            "PRODUCTION modunda video, track ve zaman aral\u0131\u011f\u0131 upstream video olay "
            "mod\u00fcl\u00fcnden gelmelidir; platform kimli\u011finden context t\u00fcretilmez."
        )
    with st.expander("Alan açıklamaları", expanded=True):
        st.markdown(
            "- `hedef_modeli`: görsel platform hipotezi\n"
            "- `tehdit_seviyesi`: görsel tehdit hipotezi; nihai Risk değildir\n"
            "- `ulke_orjini`: Registry ülkesiyle karşılaştırılan görsel ülke hipotezi\n"
            "- `gorsel_analiz`: ham görsel açıklama"
        )
    heading = st.columns([0.08, 0.92], vertical_alignment="center")
    heading[0].markdown("### 🛩️")
    heading[1].subheader("Düzenlenebilir Ham VLM JSON")
    actions = st.columns(2)
    if actions[0].button("Örnek JSON'u yükle", key="load_raw_vlm_example"):
        st.session_state.raw_vlm_json = json.dumps(RAW_VLM_EXAMPLE, ensure_ascii=False, indent=2)
    if actions[1].button("JSON'u doğrula ve formatla", key="format_raw_vlm_json"):
        try:
            parsed = parse_json_text(st.session_state.raw_vlm_json)
            st.session_state.raw_vlm_json = json.dumps(parsed, ensure_ascii=False, indent=2)
            st.success("JSON sözdizimi geçerli.")
        except json.JSONDecodeError as error:
            st.error(f"JSON sözdizimi hatası: satır {error.lineno}, sütun {error.colno}.")
    editor, catalog_panel = st.columns([0.68, 0.32])
    with editor:
        st.text_area("Ham VLM JSON", height=380, key="raw_vlm_json")
    with catalog_panel:
        with st.expander("Registry platformları", expanded=False):
            for platform in _active_platform_catalog(include_demo_inventory=runtime_mode == "DEMO"):
                st.markdown(f"**{platform['canonical_name']}**")
                st.caption(platform["user_type"])
                if platform["aliases"]:
                    st.caption(f"Kabul edilen adlar: {platform['aliases']}")

    production_video_id: str | None = None
    production_track_id: str | None = None
    production_first_seen: str | None = None
    production_last_seen: str | None = None
    production_visual_confidence: str | None = None
    if runtime_mode == "PRODUCTION":
        st.markdown("#### Upstream video / track context")
        context_columns = st.columns(2)
        with context_columns[0]:
            production_video_id = st.text_input("video_id", key="production_video_id")
            production_first_seen = st.text_input(
                "first_seen_offset_seconds", key="production_first_seen"
            )
        with context_columns[1]:
            production_track_id = st.text_input("track_id", key="production_track_id")
            production_last_seen = st.text_input(
                "last_seen_offset_seconds", key="production_last_seen"
            )
            production_visual_confidence = st.text_input(
                "visual_confidence (0.0–1.0)", key="production_visual_confidence"
            )

    analyze_buttons = st.columns(2)
    analyze_canonical = analyze_buttons[0].button(
        "VLM Çıktısını Analiz Et",
        type="primary",
        key="analyze_raw_vlm",
        use_container_width=True,
    )
    analyze_teknofest = analyze_buttons[1].button(
        "TEKNOFEST Şartname",
        key="analyze_raw_vlm_teknofest",
        use_container_width=True,
    )
    if not analyze_canonical and not analyze_teknofest:
        return
    response_format: Literal["canonical", "teknofest_spec"] = (
        "teknofest_spec" if analyze_teknofest else "canonical"
    )
    try:
        raw_vlm = parse_json_text(st.session_state.raw_vlm_json)
    except json.JSONDecodeError as error:
        st.error(f"JSON sözdizimi hatası: satır {error.lineno}, sütun {error.colno}.")
        return
    if not isinstance(raw_vlm, dict):
        st.error("Ham VLM JSON kök değeri bir object olmalıdır.")
        return

    st.session_state.analyze_result = None
    st.session_state.request_payload = None
    st.session_state.raw_adapter_result = None
    st.session_state.raw_adapter_request = None
    st.session_state.raw_vlm_submission = None
    st.session_state.raw_vlm_assessment = None

    assessment = client.analyze_raw_vlm_only(raw_vlm)
    if not assessment.ok:
        _show_api_error(assessment)
        return
    st.session_state.raw_vlm_assessment = assessment.body

    assessment_body = assessment.body if isinstance(assessment.body, dict) else {}
    resolved_platform_id = assessment_body.get("platform_id")
    try:
        first_seen = (
            float(production_first_seen)
            if production_first_seen is not None and production_first_seen.strip()
            else None
        )
        last_seen = (
            float(production_last_seen)
            if production_last_seen is not None and production_last_seen.strip()
            else None
        )
        runtime_context, is_fallback = resolve_raw_vlm_runtime_context(
            runtime_mode=runtime_mode,
            platform_id=(resolved_platform_id if isinstance(resolved_platform_id, str) else None),
            demo_track_id=f"TRK_RAW_{uuid4().hex[:10]}",
            upstream_video_id=production_video_id,
            upstream_track_id=production_track_id,
            first_seen_offset_seconds=first_seen,
            last_seen_offset_seconds=last_seen,
        )
        upstream_confidence = (
            float(production_visual_confidence)
            if production_visual_confidence is not None
            and production_visual_confidence.strip()
            else None
        )
        visual_confidence = resolve_raw_vlm_visual_confidence(
            runtime_mode=runtime_mode,
            upstream_visual_confidence=upstream_confidence,
        )
    except ValueError as error:
        st.error(str(error))
        return
    if is_fallback:
        st.warning(
            "Platform \u00e7\u00f6z\u00fcmlenemedi veya demo route bulunamad\u0131; genel "
            "DEMO_MOCK fallback context kullan\u0131l\u0131yor."
        )

    adapter_payload = {
        "raw_vlm": raw_vlm,
        **runtime_context,
        "visual_confidence": visual_confidence,
    }
    st.session_state.raw_vlm_submission = {
        "raw_vlm": raw_vlm,
        "video_id": runtime_context["video_id"],
    }
    with st.spinner("Registry, Inventory ve operasyonel tool zinciri çalıştırılıyor..."):
        adapted = client.adapt_raw_vlm(adapter_payload)
        st.session_state.raw_adapter_result = adapted
        adapted_body = _body_dict(adapted)
        canonical = adapted_body.get("analyze_request")
        if not adapted.ok or not isinstance(canonical, dict):
            _show_api_error(adapted)
            return
        st.session_state.raw_adapter_request = canonical
        analysis = client.analyze(canonical, response_format)
    _store_analysis(analysis, canonical, response_format)
    if not analysis.ok:
        _show_api_error(analysis)


def _manual_input(
    client: DemoAPIClient,
    response_format: Literal["canonical", "teknofest_spec"],
) -> None:
    uploaded = st.file_uploader("JSON dosyası yükle", type=["json"], key="manual_upload")
    if uploaded is not None:
        signature = (uploaded.name, uploaded.size)
        if signature != st.session_state.uploaded_signature:
            try:
                st.session_state.manual_json = uploaded.getvalue().decode("utf-8")
                st.session_state.uploaded_signature = signature
            except UnicodeDecodeError:
                st.error("Dosya UTF-8 JSON olarak okunamadı.")
    button_columns = st.columns(2)
    if button_columns[0].button("Formatla", key="format_json"):
        try:
            parsed = parse_json_text(st.session_state.manual_json)
            st.session_state.manual_json = json.dumps(parsed, ensure_ascii=False, indent=2)
            st.success("JSON syntax geçerli.")
        except json.JSONDecodeError as error:
            st.error(f"JSON syntax hatası: satır {error.lineno}, sütun {error.colno}.")
    if button_columns[1].button("Örnek request yükle", key="load_example"):
        st.session_state.manual_json = EXAMPLE_REQUEST.read_text(encoding="utf-8")
    st.text_area("Request JSON", height=360, key="manual_json")
    if st.button("Analizi Başlat", type="primary", key="analyze_manual"):
        try:
            payload = parse_json_text(st.session_state.manual_json)
        except json.JSONDecodeError as error:
            st.error(f"JSON syntax hatası: satır {error.lineno}, sütun {error.colno}.")
            return
        st.session_state.raw_vlm_assessment = None
        _store_analysis(client.analyze(payload, response_format), payload, response_format)


def _scenario_input(client: DemoAPIClient) -> None:
    response_format = cast(
        Literal["canonical", "teknofest_spec"],
        st.radio(
            "Hazır demo çıktı görünümü",
            ("canonical", "teknofest_spec"),
            format_func=lambda value: (
                "Ayrıntılı Analiz" if value == "canonical" else "TEKNOFEST kısa format"
            ),
            horizontal=True,
            key="demo_response_format",
        ),
    )
    st.caption(
        "Senaryo; hazır VLM, context ve mock operasyon kayıtlarıyla tek paket çalışır. "
        "Bu seçim yalnız hazır demo sunumunu değiştirir. Ham VLM analizi her zaman "
        "ayrıntılı operasyonel JSON üretir."
    )
    if st.button("Senaryo listesini yenile", key="refresh_scenarios"):
        _load_scenarios(client)
    scenarios = st.session_state.scenarios
    if not scenarios:
        st.info("Backend senaryo kataloğu henüz yüklenmedi.")
        return
    by_id = {str(item.get("scenario_id", "")): item for item in scenarios}
    selected_id = st.selectbox("Demo senaryosu", list(by_id), key="selected_scenario")
    selected = by_id[selected_id]
    st.write("**Senaryo adı:**", shown(selected.get("name")))
    st.write("**Açıklama:**", shown(selected.get("description")))
    metric_columns = st.columns(2)
    metric_columns[0].metric(
        "Beklenen verification", shown(selected.get("expected_verification_status"))
    )
    metric_columns[1].metric("Beklenen risk", shown(selected.get("expected_risk_level")))
    payload = scenario_request_payload(selected)
    if payload is None:
        st.warning(
            "Backend scenario yanıtında request_payload yok. Frontend payload uydurmadığı "
            "için hazır senaryo analizi devre dışıdır."
        )
    if (
        st.button(
            "Analizi Başlat",
            type="primary",
            key="analyze_scenario",
            disabled=payload is None,
        )
        and payload is not None
    ):
        st.session_state.raw_vlm_assessment = None
        _store_analysis(client.analyze(payload, response_format), payload, response_format)
    st.divider()
    if st.button("Tüm Demo Senaryolarını Test Et", key="all_scenarios"):
        with st.spinner("Senaryolar sırayla çalıştırılıyor..."):
            st.session_state.scenario_smoke_rows = run_demo_scenarios(client, scenarios)
    rows = st.session_state.scenario_smoke_rows
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
        downloads = st.columns(2)
        downloads[0].download_button(
            "Sonuçları CSV indir",
            rows_to_csv(rows),
            file_name="demo_scenario_smoke.csv",
            mime="text/csv",
        )
        downloads[1].download_button(
            "Sonuçları JSON indir",
            json.dumps(rows, ensure_ascii=False, indent=2),
            file_name="demo_scenario_smoke.json",
            mime="application/json",
        )


def _analysis_result(client: DemoAPIClient) -> None:
    result = st.session_state.analyze_result
    if not isinstance(result, APIResult):
        return
    st.divider()
    render_http_outcome(result.status_code, result.error_code, result.latency_ms)
    if result.status_code is None or result.status_code == 422:
        _show_api_error(result)
        return
    body = _body_dict(result)
    if body.get("schema_version") == "raw-vlm-assessment/1.0":
        st.subheader("VLM Platform ve Ülke Orijini Değerlendirmesi")
        st.write(body.get("summary_tr", ""))
        render_video_events(body)
        metrics = st.columns(4)
        metrics[0].metric("Platform", body.get("matched_platform") or "UNRESOLVED")
        metrics[1].metric("Origin", body.get("origin_comparison", "UNKNOWN"))
        metrics[2].metric("Inventory", body.get("inventory_status", "UNKNOWN"))
        metrics[3].metric("Ön Risk", body.get("risk_level", "UNKNOWN"))
        st.info(
            "Permission, Flight Plan ve NOTAM operasyon alanı ve zaman olmadığı için "
            "değerlendirilmedi. Inventory kaydı tek başına güven veya uçuş izni değildir."
        )
        if body.get("origin_comparison") == "MISMATCH":
            st.warning(body.get("origin_explanation_tr", "Ülke hipotezi uyuşmuyor."))
        st.json(body)
        return
    output = response_output(body)
    origin_assessment = st.session_state.raw_vlm_assessment
    if output and isinstance(origin_assessment, dict):
        origin_result = {
            "vlm_origin_hypothesis": origin_assessment.get("vlm_origin_hypothesis"),
            "registry_platform_origin": origin_assessment.get("registry_platform_origin"),
            "registry_manufacturer_country_code": origin_assessment.get("registry_country_code"),
            "turkey_inventory_status": origin_assessment.get("inventory_status"),
            "origin_comparison": origin_assessment.get("origin_comparison"),
            "origin_explanation_tr": origin_assessment.get("origin_explanation_tr"),
        }
        output = {**output, "country_hypothesis_assessment": origin_result}
    is_teknofest = all(key in body for key in ("summary", "events", "risk", "actions"))
    if output and not is_teknofest:
        render_raw_vlm_analysis(
            output,
            origin_assessment if isinstance(origin_assessment, dict) else {},
        )
    elif is_teknofest:
        render_teknofest_spec(body)
        if isinstance(origin_assessment, dict):
            render_video_events(origin_assessment)
        st.info(
            "Ayrıntılı operasyonel rapor için Ayrıntılı Analiz seçeneğini veya "
            "VLM Çıktısını Analiz Et düğmesini kullanın."
        )
    else:
        st.info("Final output henüz mevcut değil.")
    if result.status_code == 202 and st.session_state.pending_payload is not None:
        st.caption("GPU handoff tamamlandığında aynı parsed payload değişmeden yeniden gönderilir.")
        if st.button("Analizi Yeniden Dene", key="retry_waiting"):
            pending = st.session_state.pending_payload
            retry_format = cast(
                Literal["canonical", "teknofest_spec"],
                st.session_state.analysis_response_format,
            )
            _store_analysis(client.analyze(pending, retry_format), pending, retry_format)
            st.rerun()

    if output and not is_teknofest:
        return

    st.header("E. Teknik Detaylar")
    with st.expander("Analiz JSON'u, event trace ve raw request", expanded=False):
        json_tab_label = "TEKNOFEST Şartname JSON'u" if is_teknofest else "Ayrıntılı Analiz JSON'u"
        event_id = st.session_state.event_id
        if isinstance(event_id, str):
            columns = st.columns(2)
            if columns[0].button("Event Kaydını Getir", key="get_event"):
                event_result = client.event(event_id)
                st.session_state.event_body = event_result.body
                if not event_result.ok:
                    _show_api_error(event_result)
            if columns[1].button("Trace Getir", key="get_trace"):
                trace_result = client.trace(event_id)
                st.session_state.trace_body = trace_result.body
                if not trace_result.ok:
                    _show_api_error(trace_result)
        if isinstance(origin_assessment, dict):
            technical_tabs = st.tabs(
                [json_tab_label, "Event trace", "Gönderilen Ham VLM", "Kaynaklar"]
            )
            with technical_tabs[0]:
                st.json(output if output else body)
            with technical_tabs[1]:
                render_trace(st.session_state.trace_body)
            with technical_tabs[2]:
                st.json(st.session_state.raw_vlm_submission or {})
            with technical_tabs[3]:
                if output:
                    render_sources(output)
        else:
            technical_tabs = st.tabs(
                [json_tab_label, "Event trace", "Raw request", "Adapter sonucu", "Kaynaklar"]
            )
            with technical_tabs[0]:
                st.json(output if output else body)
            with technical_tabs[1]:
                render_trace(st.session_state.trace_body)
            with technical_tabs[2]:
                st.json(st.session_state.request_payload or {})
            with technical_tabs[3]:
                adapter = st.session_state.raw_adapter_result
                st.json(adapter.body if isinstance(adapter, APIResult) and adapter.body else {})
            with technical_tabs[4]:
                if output:
                    render_sources(output)


def main() -> None:
    """Run the Turkish wide-layout manual test UI."""
    st.set_page_config(page_title="Operational Decision V1 Demo", layout="wide")
    _initialize_state()
    runtime_mode = AppSettings().runtime_mode
    st.title("Operational Decision V1 — Manuel Test Arayüzü")
    if runtime_mode == "DEMO":
        st.warning(
            "Kayıtlar DEMO_MOCK'tur. PDF'ler operasyonel kayıt değildir. RAG karar "
            "vermez. Uçuş planı izin değildir. Görsel hipotez kesin kimlik değildir. "
            "Sistem gerçek operasyonel otoritenin yerini almaz."
        )
    else:
        st.info(
            "PRODUCTION modu: gerçek video, track, zaman, context ve görsel güven "
            "bilgileri upstream sistemden gelmelidir; demo kayıtları kullanılmaz."
        )
    with st.sidebar:
        st.header("API ayarları")
        base_url = st.text_input("API base URL", "http://127.0.0.1:8000")

        timeout = st.number_input("İstek timeout (saniye)", min_value=1, max_value=600, value=120)
    try:
        client = DemoAPIClient(base_url, float(timeout))
    except ValueError as error:
        st.error(str(error))
        return
    try:
        with st.sidebar:
            if st.button("Bağlantıyı kontrol et"):
                result = client.health()
                render_http_outcome(result.status_code, result.error_code, result.latency_ms)
                if result.status_code is None:
                    _show_api_error(result)
            if st.button("Health durumunu yenile"):
                _load_health(client)
        if st.session_state.health_body is not None:
            render_health(st.session_state.health_body, st.session_state.rag_body)

        _raw_vlm_input(client)
        _analysis_result(client)

        if runtime_mode == "DEMO":
            with st.expander("Geliştirici / Demo Modu", expanded=False):
                st.caption(
                    "Bu bölüm hazır demo senaryolarını ve canonical JSON girdisini içerir. "
                    "Mevcut 23 senaryo kendi video_id ve context kayıtlarıyla çalışır."
                )
                st.markdown("#### Platform Katalo\u011fu")
                st.dataframe(
                    _active_platform_catalog(),
                    column_order=(
                        "platform_id",
                        "canonical_name",
                        "user_type",
                        "category",
                        "inventory",
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                dev_tabs = st.tabs(["Hazır Demo Senaryosu", "Canonical JSON"])
                with dev_tabs[0]:
                    _scenario_input(client)
                with dev_tabs[1]:
                    _manual_input(client, "canonical")
    finally:
        client.close()
    st.caption(
        "Bu arayüz yalnız FastAPI istemcisidir; backend karar, risk, verification, "
        "RAG veya tool mantığını tekrar uygulamaz."
    )


if __name__ == "__main__":
    main()

"""Presentation-only Streamlit components for backend responses."""

from __future__ import annotations

import csv
import io
import json
import re
import time
from collections.abc import Iterator
from typing import Any

import streamlit as st

RISK_COLORS = {
    "LOW": "#2e7d32",
    "MEDIUM": "#ed6c02",
    "HIGH": "#d32f2f",
    "CRITICAL": "#7f0000",
    "UNKNOWN": "#616161",
}
REFERENCE_ONLY_DOCUMENT_IDS = {
    "UCUS_IZINLERINE_ILISKIN_EL_KITABI",
}
VIDEO_EVENTS_PENDING_MESSAGE = (
    "Zaman damgalı olaylar, video olay çıkarım modülü entegre edildiğinde gösterilecektir."
)


def shown(value: Any) -> Any:
    """Render absent backend values consistently without inventing content."""
    return "Mevcut değil" if value is None or value == "" else value


def response_output(body: Any) -> dict[str, Any]:
    """Return the final output object only when present in the response."""
    if not isinstance(body, dict):
        return {}
    output = body.get("output")
    return output if isinstance(output, dict) else {}


def _status_card(label: str, value: Any, *, risk: bool = False) -> None:
    rendered = str(shown(value))
    if risk:
        color = RISK_COLORS.get(rendered, RISK_COLORS["UNKNOWN"])
        st.markdown(
            f"<div style='border-left:5px solid {color};padding:.55rem'>"
            f"<small>{label}</small><br><strong>{rendered}</strong></div>",
            unsafe_allow_html=True,
        )
    else:
        st.metric(label, rendered)

def render_teknofest_spec(output: dict[str, Any]) -> None:
    """Render the TEKNOFEST object exactly as returned by the backend."""
    st.subheader("TEKNOFEST şartname çıktısı")
    st.markdown(str(shown(output.get("summary"))))
    st.metric("Risk", shown(output.get("risk")))
    events = output.get("events")
    st.write("**Olaylar:**")
    st.json(events if isinstance(events, list) else [])
    actions = output.get("actions")
    st.write("**Aksiyonlar:**")
    st.json(actions if isinstance(actions, list) else [])


def video_event_rows(output: dict[str, Any]) -> list[dict[str, Any]]:
    """Return producer event fields without deriving or formatting timestamps."""
    events = output.get("timestamped_events")
    if not isinstance(events, list):
        return []
    return [item for item in events if isinstance(item, dict)]


def render_video_events(output: dict[str, Any]) -> None:
    """Render real video events or the explicit pending-integration state."""
    events = video_event_rows(output)
    if not output.get("timestamps_available") or not events:
        st.info(VIDEO_EVENTS_PENDING_MESSAGE)
        assessment = output.get("untimestamped_visual_assessment")
        if isinstance(assessment, dict):
            st.caption("Zamansız görsel değerlendirme")
            st.write(shown(assessment.get("description_tr")))
        return
    st.write("**Zaman damgalı video olayları:**")
    for event in events:
        critical_label = " — Kritik olay" if event.get("critical_moment") is True else ""
        st.markdown(
            f"- **{shown(event.get('event_type'))}{critical_label}:** "
            f"{shown(event.get('first_seen'))} – {shown(event.get('last_seen'))}; "
            f"{shown(event.get('description_tr'))}"
        )


def render_http_outcome(
    status_code: int | None,
    error_code: str | None,
    latency_ms: int | None = None,
) -> None:
    """Explain transport statuses without interpreting domain results."""
    if status_code == 200:
        st.success("HTTP 200 — final sonuç alındı.")
    elif status_code == 202:
        st.warning("HTTP 202 — WAITING_FOR_GPU_HANDOFF")
    elif status_code == 409:
        st.warning("HTTP 409 — aynı fingerprint için aktif event bulunuyor.")
    elif status_code == 422:
        st.error("HTTP 422 — backend canonical input doğrulaması başarısız.")
    elif status_code == 503:
        st.error("HTTP 503 — servis kullanılamıyor.")
    elif status_code is not None:
        st.error(f"HTTP {status_code} — beklenmeyen API yanıtı.")
    elif error_code == "TIMEOUT":
        st.error("İstek zaman aşımına uğradı.")
    else:
        st.error("FastAPI servisine bağlantı kurulamadı.")
    if latency_ms is not None:
        st.caption(f"Yanıt süresi: {latency_ms} ms ({latency_ms / 1000:.2f} sn)")


def render_health(health: Any, rag_status: Any) -> None:
    """Render exact health component statuses, including DEGRADED."""
    health_body = health if isinstance(health, dict) else {}
    components = health_body.get("components")
    component_map = components if isinstance(components, dict) else {}
    st.subheader("Sistem durumu")
    st.metric("Top-level health", shown(health_body.get("status")))
    labels = [
        ("Operational DB", "operational_db"),
        ("Event DB", "event_memory_db"),
        ("RAG index", "rag_index"),
        ("LLM servisi (EVREN)", "ollama"),  # anahtar "ollama" olarak kaliyor - saglik sozlesmesi sabit (bkz. bootstrap.py: _vllm_probes)
        ("Canonical model", "decision_model"),
    ]
    columns = st.columns(len(labels))
    warnings: list[str] = []
    for column, (label, key) in zip(columns, labels, strict=True):
        raw = component_map.get(key)
        item = raw if isinstance(raw, dict) else {}
        status = item.get("status")
        column.metric(label, shown(status))
        detail = item.get("detail")
        if status in {"DEGRADED", "FAILED"} or detail:
            warnings.append(f"{label}: {shown(status)} — {shown(detail)}")
    if warnings:
        st.warning("\n\n".join(warnings))
    with st.expander("RAG health ayrıntısı"):
        st.json(rag_status if rag_status is not None else {})


def analysis_sidebar_data(output: dict[str, Any]) -> dict[str, Any]:
    """Return complete risk, review, and RAG detail without recomputing decisions."""
    raw_sources = output.get("rag_sources")
    if not isinstance(raw_sources, list):
        raw_sources = output.get("sources")
    return {
        "risk_explanation": output.get("risk_explanation"),
        "risk_increasing_factors": output.get("risk_increasing_factors") or [],
        "risk_reducing_factors": output.get("risk_reducing_factors") or [],
        "human_review_reasons": output.get("human_review_reasons") or [],
        "rag_summary": output.get("rag_summary"),
        "rag_decision_effect": output.get("rag_decision_effect"),
        "rag_sources": raw_sources if isinstance(raw_sources, list) else [],
    }


def render_sources(output: dict[str, Any]) -> None:
    """Render final source references and warn about reference-only leakage."""
    st.subheader("RAG kaynakları")
    raw_sources = output.get("sources")
    sources = raw_sources if isinstance(raw_sources, list) else []
    tool_value = output.get("tool_execution_summary")
    tools = tool_value if isinstance(tool_value, dict) else {}
    rag_raw = tools.get("text_rag")
    rag = rag_raw if isinstance(rag_raw, dict) else None
    if not sources:
        if rag is None:
            st.info("Text RAG policy gereği çağrılmadı.")
        elif rag.get("error_code") == "NO_RELEVANT_CONTEXT":
            st.warning("NO_RELEVANT_CONTEXT")
        st.write("Kaynak mevcut değil.")
        return
    if rag is not None and rag.get("error_code") == "NO_RELEVANT_CONTEXT":
        st.warning("NO_RELEVANT_CONTEXT")
    rows = []
    leaked: set[str] = set()
    for raw in sources:
        source = raw if isinstance(raw, dict) else {}
        document_id = str(source.get("document_id", ""))
        if document_id in REFERENCE_ONLY_DOCUMENT_IDS:
            leaked.add(document_id)
        rows.append(
            {
                "source_id": shown(source.get("source_id")),
                "document_id": shown(source.get("document_id")),
                "filename": shown(source.get("filename")),
                "page_start": shown(source.get("page_start")),
                "page_end": shown(source.get("page_end")),
                "section_title": shown(source.get("section_title")),
                "excerpt": shown(source.get("excerpt")),
            }
        )
    if leaked:
        st.error("Reference-only belge final source listesine sızdı: " + ", ".join(sorted(leaked)))
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_trace(trace: Any) -> None:
    """Render ordered lifecycle steps without recomputing their meaning."""
    if not isinstance(trace, dict):
        st.info("Trace mevcut değil.")
        return
    steps_value = trace.get("steps")
    steps = steps_value if isinstance(steps_value, list) else []
    rows = []
    for raw in steps:
        item = raw if isinstance(raw, dict) else {}
        rows.append(
            {
                "timestamp": shown(item.get("started_at_utc")),
                "step/component": shown(item.get("step_name")),
                "status": shown(item.get("step_status")),
                "latency_ms": shown(item.get("latency_ms")),
                "details/warnings": json.dumps(item.get("details"), ensure_ascii=False, default=str)
                if item.get("details") is not None
                else "Mevcut değil",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    """Serialize comparison rows for download without changing values."""
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def json_download(label: str, payload: Any, filename: str, *, key: str) -> None:
    """Offer a formatted JSON download for an already displayed backend object."""
    st.download_button(
        label,
        data=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        file_name=filename,
        mime="application/json",
        key=key,
    )


def final_report_text(output: dict[str, Any]) -> str:
    """Render current 2.1 presentation rules even for a stale session/API response."""
    from operational_decision.finalizer.turkish_report import (  # noqa: PLC0415
        build_turkish_operational_report,
        refresh_final_presentation,
    )

    if output.get("schema_version") == "final-output/2.1":
        return str(refresh_final_presentation(output)["operational_report_tr"])
    value = output.get("operational_report_tr")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return build_turkish_operational_report(output)


def decision_summary_data(output: dict[str, Any]) -> list[tuple[str, Any]]:
    """Return the binding six-field user decision summary in display order."""
    platform = output.get("matched_platform") or output.get("platform_status")
    return [
        ("Platform", platform),
        ("Inventory", output.get("inventory_status")),
        ("Verification", output.get("verification_status")),
        ("Risk", output.get("risk_level")),
        ("Decision", output.get("decision")),
        ("Human Review", output.get("human_approval_required")),
    ]


def primary_tool_rows(output: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep execution and domain outcomes separate for the five user-facing checks."""
    raw_summary = output.get("tool_execution_summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}

    def execution(tool_name: str) -> Any:
        raw = summary.get(tool_name)
        item = raw if isinstance(raw, dict) else {}
        return item.get("execution_status")

    def domain_result(tool_name: str, value: Any) -> Any:
        return shown(None) if execution(tool_name) == "SKIPPED" else shown(value)

    return [
        {
            "Kontrol": "Platform Tool",
            "Execution": shown(execution("platform_tool")),
            "Sonuç": shown(output.get("platform_status")),
        },
        {
            "Kontrol": "Turkey Inventory",
            "Execution": shown(execution("turkey_inventory_tool")),
            "Sonuç": shown(output.get("inventory_status")),
        },
        {
            "Kontrol": "Permission",
            "Execution": shown(execution("permission_flight_plan_tool")),
            "Sonuç": domain_result("permission_flight_plan_tool", output.get("permission_status")),
        },
        {
            "Kontrol": "Flight Plan",
            "Execution": shown(execution("permission_flight_plan_tool")),
            "Sonuç": domain_result("permission_flight_plan_tool", output.get("flight_plan_status")),
        },
        {
            "Kontrol": "NOTAM",
            "Execution": shown(execution("notam_tool")),
            "Sonuç": domain_result(
                "notam_tool",
                output.get("notam_operation_effect") or output.get("notam_status"),
            ),
        },
    ]


def raw_vlm_status_data(output: dict[str, Any]) -> list[tuple[str, Any]]:
    """Return the four primary user-facing status facts in display order."""
    from operational_decision.finalizer.turkish_report import (  # noqa: PLC0415
        decision_label_tr,
        risk_label_tr,
    )

    return [
        ("Platform", output.get("matched_platform") or "Platform çözümlenemedi"),
        ("Risk", risk_label_tr(output.get("risk_level"))),
        ("Nihai karar", decision_label_tr(output.get("decision"))),
        (
            "Operatör müdahalesi",
            "Acil"
            if output.get("human_review_priority") == "URGENT"
            else "Teyit gerekli"
            if output.get("human_approval_required") is True
            else "Gerekli değil",
        ),
    ]


def _typewriter(text: str, delay_seconds: float = 0.025) -> Iterator[str]:
    """Yield words with a short delay for a live-writing reveal effect."""
    words = text.split(" ")
    for index, word in enumerate(words):
        yield word + (" " if index < len(words) - 1 else "")
        time.sleep(delay_seconds)


def compact_operational_summary(output: dict[str, Any]) -> list[str]:
    """Return the finalized natural Turkish summary as at most four sentences."""
    summary = output.get("summary_tr")
    if not isinstance(summary, str) or not summary.strip():
        from operational_decision.finalizer.turkish_report import (  # noqa: PLC0415
            build_turkish_summary,
        )

        summary = build_turkish_summary(output)
    sentences = [
        item.strip() for item in re.split(r"(?<=[.!?])\s+", summary.strip()) if item.strip()
    ]
    return sentences[:4]


def _user_risk_factor(value: object) -> str:
    """Localize controlled factor text without adding or changing facts."""
    text = str(value).strip()
    text = re.sub(r"\bRULE_[A-Z0-9_]+\b", "", text)
    replacements = {
        "Permission": "uçuş izni",
        "Flight Plan": "uçuş planı",
        "Registry": "platform kaydı",
        "Inventory": "envanter",
        "Verification": "doğrulama",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return re.sub(r"\s+", " ", text).strip(" -—:;")


def compact_risk_reasons(output: dict[str, Any]) -> list[str]:
    """Return at most two increasing and two reducing verified risk factors."""
    reasons: list[str] = []
    increasing = output.get("risk_increasing_factors")
    reducing = output.get("risk_reducing_factors")
    if isinstance(increasing, list):
        reasons.extend(
            f"Artıran: {_user_risk_factor(item)}"
            for item in increasing[:2]
            if _user_risk_factor(item)
        )
    if isinstance(reducing, list):
        reasons.extend(
            f"Azaltan: {_user_risk_factor(item)}"
            for item in reducing[:2]
            if _user_risk_factor(item)
        )
    return reasons


def compact_recommended_actions(output: dict[str, Any]) -> list[str]:
    """Return at most three already-guarded finalized actions."""
    from operational_decision.finalizer.turkish_report import (  # noqa: PLC0415
        safe_action_recommendations,
    )

    return safe_action_recommendations(output)[:3]


def technical_details_available(output: dict[str, Any], origin_assessment: dict[str, Any]) -> bool:
    """Return whether the expandable technical section has meaningful data."""
    return bool(output or origin_assessment)


def _technical_registry_data(
    output: dict[str, Any], origin_assessment: dict[str, Any]
) -> dict[str, Any]:
    return {
        "platform_status": output.get("platform_status"),
        "matched_platform": output.get("matched_platform"),
        "usage_domain": output.get("platform_usage_domain"),
        "identity_scope": output.get("platform_identity_scope"),
        "variant_policy": output.get("platform_variant_policy"),
        "manufacturer_country_code": output.get("manufacturer_country_code")
        or origin_assessment.get("registry_country_code"),
        "vlm_country_hypothesis": output.get("vlm_origin_hypothesis")
        or origin_assessment.get("vlm_origin_hypothesis"),
        "country_hypothesis_explanation": origin_assessment.get("origin_explanation_tr"),
    }


def render_raw_vlm_analysis(output: dict[str, Any], origin_assessment: dict[str, Any]) -> None:
    """Render one canonical result with operational content first and details collapsed."""
    st.header("1. Durum kartı")
    columns = st.columns(4)
    for column, (label, value) in zip(columns, raw_vlm_status_data(output), strict=True):
        with column:
            _status_card(label, value, risk=label == "Risk")

    st.header("2. Kısa operasyonel özet")
    summary_text = " ".join(compact_operational_summary(output))
    if st.session_state.get("_last_streamed_summary") == summary_text:
        st.markdown(summary_text)
    else:
        st.write_stream(_typewriter(summary_text))
        st.session_state["_last_streamed_summary"] = summary_text
    render_video_events(output)

    st.header("3. Risk gerekçesi")
    reasons = compact_risk_reasons(output)
    if reasons:
        for reason in reasons:
            st.markdown(f"- {reason}")
    else:
        st.info("Ek risk gerekçesi bulunmuyor.")

    st.header("4. Önerilen aksiyonlar")
    actions = compact_recommended_actions(output)
    if actions:
        for index, action in enumerate(actions, 1):
            st.markdown(f"{index}. {action}")
    else:
        st.info("Ek aksiyon önerilmedi.")

    if technical_details_available(output, origin_assessment):
        with st.expander("5. Teknik detaylar", expanded=False):
            registry_tab, records_tab, verification_tab, rag_tab, guard_tab, json_tab = st.tabs(
                [
                    "Registry ve ülke",
                    "Operasyon kayıtları",
                    "Doğrulama",
                    "RAG kaynakları",
                    "Guard düzeltmeleri",
                    "Tam JSON",
                ]
            )
            with registry_tab:
                st.json(_technical_registry_data(output, origin_assessment))
                st.caption(
                    "Registry üretici ülkesi yalnız üretim metadata’sıdır; operatör veya "
                    "aidiyet kanıtı değildir."
                )
            with records_tab:
                st.write("**Inventory**", shown(output.get("inventory_status")))
                st.write("**Permission**", shown(output.get("permission_status")))
                permission_details = output.get("permission_details")
                if isinstance(permission_details, list) and permission_details:
                    st.dataframe(permission_details, use_container_width=True, hide_index=True)
                st.write("**Flight Plan**", shown(output.get("flight_plan_status")))
                flight_plan_details = output.get("flight_plan_details")
                if isinstance(flight_plan_details, list) and flight_plan_details:
                    st.dataframe(flight_plan_details, use_container_width=True, hide_index=True)
                st.write(
                    "**NOTAM**",
                    shown(output.get("notam_operation_effect") or output.get("notam_status")),
                )
                notam_details = output.get("notam_details")
                if isinstance(notam_details, list) and notam_details:
                    st.write("**Eşleşen NOTAM kayıtları**")
                    st.dataframe(notam_details, use_container_width=True, hide_index=True)
                else:
                    st.caption("Bu olay için eşleşen aktif NOTAM kaydı yok.")
                st.dataframe(primary_tool_rows(output), use_container_width=True, hide_index=True)
            with verification_tab:
                st.write("**Verification**", shown(output.get("verification_status")))
                st.write(
                    "**Verification reason codes**", shown(output.get("verification_reason_codes"))
                )
                st.write(
                    "**Operational consistency**",
                    shown(output.get("operational_consistency_status")),
                )
                st.write(
                    "**Consistency flags**", shown(output.get("operational_consistency_flags"))
                )
                st.write("**Ayrıntılı teknik rapor**")
                st.write(final_report_text(output))
            with rag_tab:
                st.write("**RAG özeti**", shown(output.get("rag_summary")))
                st.write("**Karara etkisi**", shown(output.get("rag_decision_effect")))
                render_sources(output)
            with guard_tab:
                st.json(output.get("guard_corrections") or [])
            with json_tab:
                st.json(output)
                json_download(
                    "Tam JSON'u indir",
                    output,
                    "operational_decision.json",
                    key="download_operational_decision_json",
                )

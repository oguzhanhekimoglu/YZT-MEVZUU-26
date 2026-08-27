"""Video-geneli özet — TYDA şartnamesinin istediği {summary, events, risk,
actions} biçiminde tek bir çıktı.

Yeni bir değerlendirme YAPMAZ: bir video oturumu boyunca her hedef için zaten
üretilip event_memory.db'ye kaydedilmiş FinalDecisionOutput kayıtlarını
(bkz. EventService.list_finalized_outputs_for_video) tek bir LLM çağrısıyla
Türkçe bir anlatıya sentezler — özet cümlesi bu zaten var olan, hedef-bazlı
nihai analizlere dayanır.
"""

import json
import logging
from datetime import datetime
from typing import Any

from operational_decision.llm.base_client import BaseLLMClient
from operational_decision.memory.event_service import EventService

log = logging.getLogger(__name__)

# BUG-FIX: sabit 800 token'lık varsayılan, birden çok hedef analizini tek
# JSON'da birleştiren bu sentezde çıktının yarıda kesilip geçersiz JSON
# üretmesine (JSONDecodeError: Unterminated string) yol açıyordu.
_MAX_TOKENS = 3000

_PENDING_RESULT: dict[str, Any] = {
    "status": "pending",
    "summary": "",
    "events": [],
    "risk": "bilinmiyor",
    "actions": [],
}


def _video_summary_json_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "time": {"type": "string"},
                        "event": {"type": "string"},
                        "critical": {"type": "boolean"},
                    },
                    "required": ["time", "event", "critical"],
                },
            },
            "risk": {
                "type": "string",
                "enum": ["düşük", "orta", "yüksek", "kritik", "bilinmiyor"],
            },
            "actions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "events", "risk", "actions"],
    }


def _format_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")
    return "?"


def _is_critical(output: dict[str, Any]) -> bool:
    """Deterministik kritiklik: LLM'in serbestçe uydurmasına bırakılmaz,
    zaten üretilmiş nihai analizin kendi bayraklarından/riskinden türetilir."""
    if output.get("hostile_target_confirmed") or output.get("legal_violation_confirmed"):
        return True
    return str(output.get("risk_level", "")).upper() in {"HIGH", "CRITICAL"}


def _describe_output(row: dict[str, Any]) -> str:
    output = row.get("output") or {}
    identity = output.get("canonical_name") or output.get("matched_platform") or "Bilinmeyen hedef"
    risk = output.get("risk_level", "UNKNOWN")
    summary = output.get("summary_tr", "")
    action_texts = [
        action.get("reason_tr") or action.get("action_code", "")
        for action in output.get("recommended_actions", [])
        if isinstance(action, dict)
    ]
    time_label = _format_time(row.get("created_at_utc"))
    critical_tag = " [KRİTİK]" if _is_critical(output) else ""
    line = f"- [{time_label}]{critical_tag} {identity} — risk: {risk}. {summary}"
    if action_texts:
        line += f" Öneriler: {', '.join(action_texts)}"
    return line


def _build_prompt(outputs: list[dict[str, Any]]) -> list[dict[str, str]]:
    joined = "\n".join(_describe_output(row) for row in outputs)
    instruction = (
        "Aşağıda bir video oturumu boyunca tespit edilen hedeflerin, ZATEN "
        "ÜRETİLMİŞ bireysel analiz sonuçları listeleniyor. Bu bilgilere "
        "DAYANARAK — yeni bilgi uydurmadan, sadece verilenleri birleştirerek — "
        "videonun genelini özetleyen TEK bir Türkçe paragraf, olayların zaman "
        "damgalı kısa listesi, videonun genel risk seviyesi (verilen bireysel "
        "risklerin en yükseğini yansıtmalı) ve tekrarsız, birleştirilmiş bir "
        "aksiyon önerisi listesi üret. Her olay için 'critical' alanını SADECE "
        "girdide '[KRİTİK]' etiketiyle işaretli bir analize karşılık geliyorsa "
        "true yap, diğer tüm olaylarda false yap — kendi başına yeni bir "
        "kritiklik değerlendirmesi uydurma.\n\n"
        f"BİREYSEL ANALİZLER:\n{joined}"
    )
    return [{"role": "user", "content": instruction}]


async def summarize_video(
    *,
    video_id: str,
    event_service: EventService,
    llm_client: BaseLLMClient,
) -> dict[str, Any]:
    """O videoya ait tüm hedef-bazlı nihai kararlardan tek bir video-geneli özet üretir."""
    outputs = await event_service.list_finalized_outputs_for_video(video_id)
    if not outputs:
        return dict(_PENDING_RESULT)

    messages = _build_prompt(outputs)
    try:
        raw = await llm_client.generate(
            messages, response_schema=_video_summary_json_schema(), max_tokens=_MAX_TOKENS
        )
        parsed = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 - en iyi çaba sentezi, herhangi bir hata "partial"a düşmeli
        log.warning("[VIDEO-OZET] video_id=%s için özet üretilemedi: %s", video_id, exc)
        return {
            "status": "partial",
            "summary": "Video geneli özet üretilemedi (LLM hatası).",
            "events": [],
            "risk": "bilinmiyor",
            "actions": [],
        }

    return {
        "status": "final",
        "summary": parsed.get("summary", ""),
        "events": parsed.get("events", []),
        "risk": parsed.get("risk", "bilinmiyor"),
        "actions": parsed.get("actions", []),
    }

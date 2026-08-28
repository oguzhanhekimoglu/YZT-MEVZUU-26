"""Video-geneli özet — TYDA şartnamesinin istediği {summary, events, risk,
actions} biçiminde tek bir çıktı.

Yeni bir değerlendirme YAPMAZ: bir video oturumu boyunca her hedef için zaten
üretilip event_memory.db'ye kaydedilmiş FinalDecisionOutput kayıtlarından
gerçek zaman damgalı, DETERMİNİSTİK bir olay günlüğü (video başlatıldı ->
her güvenilir tespit) üretir.

BUG-FIX (mimari değişiklik — kullanıcı isteği): önceki sürüm bunu tek bir LLM
çağrısıyla serbest Türkçe metne dönüştürüyordu. Bu hem yavaştı (20-40+ saniye),
hem güvenilmezdi (zaman zaman kimlik doğrulama/zaman aşımı hatası, çok uzun
prompt'ta JSON'un yarıda kesilmesi), hem de nihai çıktı artık "uçak ismi"
yerine ham, gerçek zaman damgalı bir olay listesi olarak isteniyor — bunun
için LLM'in serbest yorumuna hiç gerek yok, zaten elimizdeki veriden
birebir üretilebilir. Bu yüzden LLM çağrısı TAMAMEN KALDIRILDI: artık ne
zaman aşımı, ne kimlik doğrulama hatası, ne de JSON kesilmesi riski var.
"""

from datetime import datetime
from typing import Any

from operational_decision.memory.event_service import EventService

# BUG-FIX: event_memory.db aynı video_id için oturumlar arası hiç
# temizlenmiyor — aynı dosya defalarca test edildikçe kayıt sayısı sınırsız
# büyüyebiliyordu (bir örnekte 240 kayıt). Denetim izi (audit trail)
# korunuyor — event_memory.db'den hiçbir şey silinmiyor — sadece bu okuma en
# yeni kayıtların oluşturduğu sınırlı bir pencereye bakıyor.
_MAX_RAW_RECORDS = 250

# Ardışık tekrarları birleştirdikten sonra bile grup sayısı büyüyebilir —
# olay listesinin sınırsız büyümesini önlemek için en fazla bu kadar grup
# (en yenisi öncelikli) olay günlüğüne dahil edilir.
_MAX_GROUPS_IN_EVENTS = 60

# BUG-FIX ("nihai çıktı bazen hiç gelmiyor" — kök neden araştırması):
# burada AYRICA bir "en az 2 kez görülmeli" güvenilirlik filtresi vardı, ama
# bu filtre TÜM VİDEONUN karışık hedef akışında "ardışık komşu satır" sayıyordu
# - videoda gerçekten var olan TEK bir uçak yalnızca BİR KEZ (kendi track'i
# için) doğrulanıp kaydedildiğinde bu "grup boyu 1" oluyor ve (kritik
# değilse) yanlışlıkla "güvenilmez" sayılıp özetten düşebiliyordu. Asıl
# güvenilirlik garantisi artık KAYNAĞINDA veriliyor: pipeline.py'deki
# _confirm_stable_vlm_hash, bir hedefin kimliği (araç sınıfı/tip/model/ülke)
# 2 ardışık analizde DEĞİŞMEDEN kalmadıkça event_memory.db'ye hiç yazmıyor.
# Yani buraya ulaşan her kayıt zaten kaynağında doğrulanmış - burada ikinci
# bir (ve yanlış granülerlikte) filtre uygulamak gereksiz ve zararlıydı.
_RISK_LABELS = {
    "LOW": "düşük",
    "MEDIUM": "orta",
    "HIGH": "yüksek",
    "CRITICAL": "kritik",
}
_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

_PENDING_RESULT: dict[str, Any] = {
    "status": "pending",
    "summary": "",
    "events": [],
    "risk": "bilinmiyor",
    "actions": [],
}


def _format_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")
    return "?"


def _risk_label(risk_level: Any) -> str:
    return _RISK_LABELS.get(str(risk_level).upper(), "bilinmiyor")


def _is_critical(output: dict[str, Any]) -> bool:
    """Deterministik kritiklik: LLM'in serbestçe uydurmasına bırakılmaz,
    zaten üretilmiş nihai analizin kendi bayraklarından/riskinden türetilir."""
    if output.get("hostile_target_confirmed") or output.get("legal_violation_confirmed"):
        return True
    return str(output.get("risk_level", "")).upper() in {"HIGH", "CRITICAL"}


def _identity_and_risk(row: dict[str, Any]) -> tuple[str, str]:
    output = row.get("output") or {}
    identity = output.get("canonical_name") or output.get("matched_platform") or "Bilinmeyen hedef"
    return identity, str(output.get("risk_level", "UNKNOWN")).upper()


def _group_consecutive_repeats(outputs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Collapse consecutive re-analyses of the same identity+risk into one group.

    BUG-FIX: a continuously tracked object is re-analyzed every few seconds,
    so a single video session can accumulate hundreds of near-identical
    per-target records. Grouping only merges ADJACENT (chronologically
    consecutive) identical identity+risk pairs, so genuinely different
    targets/events are never collapsed together.
    """
    groups: list[list[dict[str, Any]]] = []
    for row in outputs:
        if groups and _identity_and_risk(groups[-1][-1]) == _identity_and_risk(row):
            groups[-1].append(row)
        else:
            groups.append([row])
    return groups


def _group_event(group: list[dict[str, Any]]) -> dict[str, Any]:
    last = group[-1]
    identity, risk = _identity_and_risk(last)
    critical = any(_is_critical(row.get("output") or {}) for row in group)
    repeat_note = f" ({len(group)} kez tespit edildi)" if len(group) > 1 else ""
    # Olayın zamanı, o hipotezin İLK görüldüğü an — kullanıcı örneğiyle
    # uyumlu ("23:58:59'da X tespit edildi, ..."): "ne zaman oldu" sorusunun
    # doğal cevabı ilk gözlem anıdır, en son tekrarın anı değil.
    return {
        "time": _format_time(group[0].get("created_at_utc")),
        "event": f"{identity} tespit edildi{repeat_note} — risk: {_risk_label(risk)}",
        "critical": critical,
    }


def _collect_unique_actions(groups: list[list[dict[str, Any]]]) -> list[str]:
    seen: list[str] = []
    for group in groups:
        output = group[-1].get("output") or {}
        for action in output.get("recommended_actions", []):
            if not isinstance(action, dict):
                continue
            text = action.get("reason_tr") or action.get("action_code", "")
            if text and text not in seen:
                seen.append(text)
    return seen


def _overall_risk_label(groups: list[list[dict[str, Any]]]) -> str:
    levels = [_identity_and_risk(group[-1])[1] for group in groups]
    known = [level for level in levels if level in _RISK_ORDER]
    if not known:
        return "bilinmiyor"
    return _risk_label(max(known, key=lambda level: _RISK_ORDER[level]))


async def summarize_video(
    *,
    video_id: str,
    event_service: EventService,
    since: datetime | None = None,
) -> dict[str, Any]:
    """O videoya ait tüm hedef-bazlı nihai kararlardan gerçek zaman damgalı,
    deterministik bir olay günlüğü üretir (LLM çağrısı yapmaz).

    `since` verilirse (bkz. routes_events.py - çağıran oturumun başlangıç
    zamanı) yalnızca o andan sonraki kayıtlar kullanılır ve ilk olay olarak
    "Video başlatıldı" eklenir; aynı video_id (dosya adı) önceki oturumlarda
    tekrar tekrar test edilmiş olsa bile eski oturumların kayıtları bu
    özete karışmaz.
    """
    outputs = await event_service.list_finalized_outputs_for_video(video_id, since=since)

    events: list[dict[str, Any]] = []
    if since is not None:
        events.append({"time": _format_time(since), "event": "Video başlatıldı", "critical": False})

    if not outputs:
        if events:
            return {
                "status": "final",
                "summary": "Video başlatıldı, henüz güvenilir bir tespit yok.",
                "events": events,
                "risk": "bilinmiyor",
                "actions": [],
            }
        return dict(_PENDING_RESULT)

    recent = outputs[-_MAX_RAW_RECORDS:]
    groups = _group_consecutive_repeats(recent)[-_MAX_GROUPS_IN_EVENTS:]

    events.extend(_group_event(group) for group in groups)
    overall_risk = _overall_risk_label(groups)

    return {
        "status": "final",
        "summary": f"{len(groups)} güvenilir tespit kaydedildi; en yüksek risk: {overall_risk}.",
        "events": events,
        "risk": overall_risk,
        "actions": _collect_unique_actions(groups),
    }

"""Unit tests for the video-geneli özet (video_summary.summarize_video).

BUG-FIX (mimari değişiklik): video_summary artık LLM çağrısı yapmıyor —
gerçek zaman damgalı, deterministik bir olay günlüğü üretiyor. Bu dosyadaki
testler de buna göre yeniden yazıldı (eski LLM-tabanlı testler kaldırıldı).
"""

from datetime import UTC, datetime, timedelta

import pytest

from operational_decision.contracts.common import EventStatus
from operational_decision.decision.video_summary import summarize_video
from operational_decision.memory.database import EventMemoryDatabase
from operational_decision.memory.event_service import EventService
from operational_decision.persistence.sqlite_database import serialize_utc, utc_now


class FakeEventService:
    """Duck-typed EventService stub returning canned finalized outputs."""

    def __init__(self, outputs: list[dict]) -> None:
        self._outputs = outputs
        self.last_since: datetime | None = None

    async def list_finalized_outputs_for_video(
        self, video_id: str, *, since: datetime | None = None
    ) -> list[dict]:
        self.last_since = since
        if since is None:
            return self._outputs
        return [row for row in self._outputs if row.get("created_at_utc") and row["created_at_utc"] >= since]


@pytest.mark.asyncio
async def test_summarize_video_returns_pending_when_no_finalized_events_and_no_session() -> None:
    service = FakeEventService([])

    result = await summarize_video(video_id="video-1", event_service=service)

    assert result["status"] == "pending"
    assert result["events"] == []


@pytest.mark.asyncio
async def test_summarize_video_reports_session_started_even_without_detections_yet() -> None:
    session_start = datetime(2026, 1, 1, 23, 58, 29, tzinfo=UTC)
    service = FakeEventService([])

    result = await summarize_video(video_id="video-1", event_service=service, since=session_start)

    assert result["status"] == "final"
    assert result["events"] == [{"time": "23:58:29", "event": "Video başlatıldı", "critical": False}]


@pytest.mark.asyncio
async def test_summarize_video_builds_deterministic_timestamped_event_log() -> None:
    """Kullanıcı isteği: nihai çıktı artık serbest bir LLM paragrafı değil,
    gerçek zaman damgalarıyla bir olay günlüğü — "23:58:29'da video
    başlatıldı", "23:58:59'da F-35 tespit edildi — risk: yüksek" gibi."""
    session_start = datetime(2026, 1, 1, 23, 58, 29, tzinfo=UTC)
    detection_time = datetime(2026, 1, 1, 23, 58, 59, tzinfo=UTC)
    f35 = {"canonical_name": "F-35A Lightning II", "risk_level": "HIGH"}
    outputs = [
        {"output": f35, "created_at_utc": detection_time},
        {"output": f35, "created_at_utc": detection_time + timedelta(seconds=1)},
    ]
    service = FakeEventService(outputs)

    result = await summarize_video(video_id="video-1", event_service=service, since=session_start)

    assert result["status"] == "final"
    assert result["events"] == [
        {"time": "23:58:29", "event": "Video başlatıldı", "critical": False},
        {
            "time": "23:58:59",
            "event": "F-35A Lightning II tespit edildi (2 kez tespit edildi) — risk: yüksek",
            "critical": True,
        },
    ]
    assert result["risk"] == "yüksek"


@pytest.mark.asyncio
async def test_summarize_video_tags_only_hostile_or_high_risk_outputs_as_critical() -> None:
    """Şartname: kritik anlar açıkça vurgulanmalı — bu bayrak LLM'in serbest
    yorumuna değil, nihai analizin kendi bayrağına/riskine dayanmalı."""
    outputs = [
        {"output": {"canonical_name": "Sivil hedef", "risk_level": "LOW"}, "created_at_utc": None},
        {"output": {"canonical_name": "Sivil hedef", "risk_level": "LOW"}, "created_at_utc": None},
        {
            "output": {"canonical_name": "Düşman hedef", "hostile_target_confirmed": True, "risk_level": "LOW"},
            "created_at_utc": None,
        },
        {"output": {"canonical_name": "Yüksek riskli hedef", "risk_level": "HIGH"}, "created_at_utc": None},
    ]
    service = FakeEventService(outputs)

    result = await summarize_video(video_id="video-1", event_service=service)

    by_identity = {event["event"].split(" tespit")[0]: event["critical"] for event in result["events"]}
    assert by_identity["Sivil hedef"] is False
    assert by_identity["Düşman hedef"] is True
    assert by_identity["Yüksek riskli hedef"] is True


@pytest.mark.asyncio
async def test_summarize_video_collapses_consecutive_repeats_of_same_target() -> None:
    """BUG-FIX regresyonu: sürekli takip edilen tek bir hedef her birkaç
    saniyede bir yeniden analiz edildiğinde yüzlerce neredeyse özdeş kayıt
    birikebiliyordu; bunların hepsi tek bir olaya düşmeli (bkz.
    _group_consecutive_repeats)."""
    repeated = {"canonical_name": "F-35A Lightning II", "risk_level": "HIGH"}
    other = {"canonical_name": "Kaan", "risk_level": "MEDIUM"}
    outputs = (
        [{"output": repeated, "created_at_utc": None} for _ in range(50)]
        + [{"output": other, "created_at_utc": None} for _ in range(2)]
        + [{"output": repeated, "created_at_utc": None} for _ in range(5)]
    )
    service = FakeEventService(outputs)

    result = await summarize_video(video_id="video-1", event_service=service)

    events_text = [event["event"] for event in result["events"]]
    assert sum("F-35A Lightning II" in text for text in events_text) == 2
    assert any("(50 kez tespit edildi)" in text for text in events_text)
    assert any("(5 kez tespit edildi)" in text for text in events_text)
    assert any("Kaan" in text for text in events_text)


@pytest.mark.asyncio
async def test_summarize_video_caps_raw_records_to_recent_window() -> None:
    """BUG-FIX regresyonu: aynı video_id oturumlar arası hiç temizlenmediği
    için (event_memory.db kalıcı bir denetim izi) kayıt sayısı sınırsız
    büyüyebiliyordu. Sentez artık yalnızca en yeni _MAX_RAW_RECORDS kaydına
    bakıyor — denetim izinin kendisi (event_memory.db) hiçbir şekilde
    değişmiyor."""
    dropped = {"canonical_name": "Pencere Disinda Kalan Hedef", "risk_level": "LOW"}
    kept = {"canonical_name": "Pencere Icindeki Hedef", "risk_level": "LOW"}
    # 10 kayit kesinlikle pencerenin (son 250) disinda kalacak sekilde en basta.
    outputs = [{"output": dropped, "created_at_utc": None} for _ in range(10)] + [
        {"output": kept, "created_at_utc": None} for _ in range(250)
    ]
    service = FakeEventService(outputs)

    result = await summarize_video(video_id="video-1", event_service=service)

    events_text = [event["event"] for event in result["events"]]
    assert any("Pencere Icindeki Hedef" in text for text in events_text)
    assert not any("Pencere Disinda Kalan Hedef" in text for text in events_text)


@pytest.mark.asyncio
async def test_summarize_video_since_excludes_previous_sessions_of_same_video_id() -> None:
    """BUG-FIX: aynı video_id (dosya adı) farklı oturumlarda tekrar tekrar
    test edildiğinde, önceki oturumlardan kalma kayıtlar hâlâ aynı video_id
    altında birikip yeni oturumun özetine karışıyordu ("eski çıktıları baz
    alarak cevap üretiyor"). `since` (mevcut oturumun başlangıç zamanı)
    verildiğinde önceki oturumların kayıtları tamamen dışlanmalı."""
    previous_session = {"canonical_name": "Onceki Oturum Hedefi", "risk_level": "LOW"}
    current_session = {"canonical_name": "Mevcut Oturum Hedefi", "risk_level": "LOW"}
    session_start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    outputs = [
        {"output": previous_session, "created_at_utc": session_start - timedelta(hours=1)},
        {"output": current_session, "created_at_utc": session_start + timedelta(seconds=5)},
        {"output": current_session, "created_at_utc": session_start + timedelta(seconds=6)},
    ]
    service = FakeEventService(outputs)

    result = await summarize_video(video_id="video-1", event_service=service, since=session_start)

    assert service.last_since == session_start
    events_text = [event["event"] for event in result["events"]]
    assert any("Mevcut Oturum Hedefi" in text for text in events_text)
    assert not any("Onceki Oturum Hedefi" in text for text in events_text)


@pytest.mark.asyncio
async def test_summarize_video_keeps_single_confirmed_hit_even_when_not_critical() -> None:
    """BUG-FIX (kök neden araştırması — "nihai çıktı bazen hiç gelmiyor"):
    video_summary artık kendi tarafında "en az 2 kez görülmeli" gibi ikinci
    bir güvenilirlik filtresi UYGULAMAZ. Buraya (event_memory.db'ye) ulaşan
    her kayıt zaten pipeline.py'deki _confirm_stable_vlm_hash sayesinde
    kaynağında doğrulanmıştır — videoda gerçekten var olan tek bir uçak
    yalnızca BİR KEZ (kendi track'i için) kaydedilmiş olsa bile, kritik
    olmasa dahi özetten düşmemeli."""
    confirmed_once = {"canonical_name": "Tek Kayitli Ama Dogrulanmis Hedef", "risk_level": "LOW"}
    outputs = [{"output": confirmed_once, "created_at_utc": None}]
    service = FakeEventService(outputs)

    result = await summarize_video(video_id="video-1", event_service=service)

    events_text = [event["event"] for event in result["events"]]
    assert any("Tek Kayitli Ama Dogrulanmis Hedef" in text for text in events_text)


@pytest.mark.asyncio
async def test_summarize_video_keeps_single_critical_hit() -> None:
    """Tek seferlik bile olsa kritik işaretli bir bulgu (ör. gerçekten
    düşman/yüksek riskli onaylı bir hedef, kısa süre görünüp kaybolmuş
    olabilir) özete girmeli."""
    critical_once = {"canonical_name": "Kritik Tek Gorunum", "risk_level": "HIGH"}
    outputs = [{"output": critical_once, "created_at_utc": None}]
    service = FakeEventService(outputs)

    result = await summarize_video(video_id="video-1", event_service=service)

    events_text = [event["event"] for event in result["events"]]
    assert any("Kritik Tek Gorunum" in text for text in events_text)


@pytest.mark.asyncio
async def test_summarize_video_aggregates_unique_actions_and_overall_risk() -> None:
    outputs = [
        {
            "output": {
                "canonical_name": "Bayraktar TB2",
                "risk_level": "LOW",
                "recommended_actions": [{"action_code": "OBSERVE", "reason_tr": "Gözlem sürdürülsün"}],
            },
            "created_at_utc": None,
        }
        for _ in range(2)
    ] + [
        {
            "output": {
                "canonical_name": "F-15 Eagle",
                "risk_level": "HIGH",
                "recommended_actions": [{"action_code": "ESCALATE", "reason_tr": "Yetkiliye bildir"}],
            },
            "created_at_utc": None,
        }
        for _ in range(2)
    ]
    service = FakeEventService(outputs)

    result = await summarize_video(video_id="video-1", event_service=service)

    assert result["risk"] == "yüksek"
    assert result["actions"] == ["Gözlem sürdürülsün", "Yetkiliye bildir"]


@pytest.mark.asyncio
async def test_list_finalized_outputs_for_video_filters_by_video_id_and_status(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """event_repository.list_finalized_outputs_for_video — sadece o videonun
    FINALIZED event'lerini döner, diğer videoları ve tamamlanmamışları hariç tutar."""
    db = EventMemoryDatabase(tmp_path / "event_memory.db")
    await db.initialize()
    service = EventService(db)
    now = utc_now()

    async with db.transaction() as connection:
        await service.repository.insert_event(
            connection, event_id="evt-a", request_id="req-a", created_at_utc=now,
            video_id="video-1", track_id="1",
        )
        await service.repository.insert_event(
            connection, event_id="evt-b", request_id="req-b", created_at_utc=now,
            video_id="video-1", track_id="2",
        )
        await service.repository.insert_event(
            connection, event_id="evt-other-video", request_id="req-c", created_at_utc=now,
            video_id="video-2", track_id="1",
        )
        # evt-b bilerek FINALIZED yapılmıyor — sorgu bunu hariç tutmalı.
        await connection.execute(
            "UPDATE events SET event_status = ? WHERE event_id IN (?, ?)",
            (EventStatus.FINALIZED.value, "evt-a", "evt-other-video"),
        )

    await service.store_final_output("evt-a", "final-output/2.1", {"canonical_name": "A"})
    await service.store_final_output("evt-b", "final-output/2.1", {"canonical_name": "B"})
    await service.store_final_output("evt-other-video", "final-output/2.1", {"canonical_name": "C"})

    outputs = await service.list_finalized_outputs_for_video("video-1")

    assert [row["output"]["canonical_name"] for row in outputs] == ["A"]


@pytest.mark.asyncio
async def test_list_finalized_outputs_for_video_since_excludes_earlier_sessions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """BUG-FIX: gercek DB uzerinde - `since` verildiginde, ayni video_id'nin
    ONCEKI bir oturumda (daha erken created_at_utc ile) uretilmis kaydi
    disarida birakilmali, SONRAKI (mevcut oturum) kaydi dahil edilmeli."""
    db = EventMemoryDatabase(tmp_path / "event_memory.db")
    await db.initialize()
    service = EventService(db)
    earlier = utc_now()
    later = earlier + timedelta(minutes=10)

    async with db.transaction() as connection:
        await service.repository.insert_event(
            connection, event_id="evt-earlier", request_id="req-earlier", created_at_utc=earlier,
            video_id="video-1", track_id="1",
        )
        await service.repository.insert_event(
            connection, event_id="evt-later", request_id="req-later", created_at_utc=later,
            video_id="video-1", track_id="1",
        )
        await connection.execute(
            "UPDATE events SET event_status = ? WHERE event_id IN (?, ?)",
            (EventStatus.FINALIZED.value, "evt-earlier", "evt-later"),
        )

    await service.store_final_output("evt-earlier", "final-output/2.1", {"canonical_name": "ONCEKI_OTURUM"})
    await service.store_final_output("evt-later", "final-output/2.1", {"canonical_name": "MEVCUT_OTURUM"})
    # store_final_output kendi created_at_utc'sini utc_now() ile belirliyor
    # (parametre olarak alınmıyor) - testin zamanlamaya bağlı (flaky)
    # olmaması için final_outputs.created_at_utc burada kesin değerlere
    # ayarlanıyor.
    async with db.transaction() as connection:
        await connection.execute(
            "UPDATE final_outputs SET created_at_utc = ? WHERE event_id = ?",
            (serialize_utc(earlier), "evt-earlier"),
        )
        await connection.execute(
            "UPDATE final_outputs SET created_at_utc = ? WHERE event_id = ?",
            (serialize_utc(later), "evt-later"),
        )

    session_boundary = earlier + timedelta(minutes=5)
    outputs = await service.list_finalized_outputs_for_video("video-1", since=session_boundary)

    assert [row["output"]["canonical_name"] for row in outputs] == ["MEVCUT_OTURUM"]

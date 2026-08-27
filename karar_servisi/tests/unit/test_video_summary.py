"""Unit tests for the video-geneli özet (video_summary.summarize_video)."""

import json
from datetime import UTC, datetime

import pytest

from operational_decision.contracts.common import EventStatus
from operational_decision.decision.video_summary import summarize_video
from operational_decision.memory.database import EventMemoryDatabase
from operational_decision.memory.event_service import EventService
from operational_decision.persistence.sqlite_database import utc_now


class FakeLLMClient:
    """Duck-typed BaseLLMClient stub — canned response or a forced error."""

    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.last_messages: list[dict[str, str]] | None = None
        self.last_schema: dict[str, object] | None = None
        self.last_max_tokens: int | None = None

    async def generate(self, messages, *, response_schema=None, max_tokens=800) -> str:  # type: ignore[no-untyped-def]
        self.last_messages = list(messages)
        self.last_schema = response_schema
        self.last_max_tokens = max_tokens
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response

    async def unload(self) -> None:
        return None


class FakeEventService:
    """Duck-typed EventService stub returning canned finalized outputs."""

    def __init__(self, outputs: list[dict]) -> None:
        self._outputs = outputs

    async def list_finalized_outputs_for_video(self, video_id: str) -> list[dict]:
        return self._outputs


@pytest.mark.asyncio
async def test_summarize_video_returns_pending_when_no_finalized_events() -> None:
    llm = FakeLLMClient()
    service = FakeEventService([])

    result = await summarize_video(video_id="video-1", event_service=service, llm_client=llm)

    assert result["status"] == "pending"
    assert result["events"] == []
    assert llm.last_messages is None  # hiç LLM çağrısı yapılmadı


@pytest.mark.asyncio
async def test_summarize_video_synthesizes_from_final_outputs() -> None:
    canned = {
        "summary": "Videoda bir İHA gözlemlendi, tehdit seviyesi düşük.",
        "events": [{"time": "00:05", "event": "İHA tespit edildi", "critical": False}],
        "risk": "düşük",
        "actions": ["Gözlem sürdürülsün"],
    }
    llm = FakeLLMClient(response=json.dumps(canned, ensure_ascii=False))
    outputs = [
        {
            "output": {
                "canonical_name": "Bayraktar TB2",
                "risk_level": "LOW",
                "summary_tr": "Bilinen bir İHA modeli, tehdit oluşturmuyor.",
                "recommended_actions": [{"action_code": "OBSERVE", "reason_tr": "Gözlem sürdürülsün"}],
            },
            "created_at_utc": datetime(2026, 1, 1, 10, 0, 5, tzinfo=UTC),
        }
    ]
    service = FakeEventService(outputs)

    result = await summarize_video(video_id="video-1", event_service=service, llm_client=llm)

    assert result["status"] == "final"
    assert result["summary"] == canned["summary"]
    assert result["events"] == canned["events"]
    assert result["risk"] == "düşük"
    assert result["actions"] == canned["actions"]
    # nihai analiz (Bayraktar TB2 / özet metni) prompt'a gerçekten dahil edildi
    assert llm.last_messages is not None
    prompt_text = llm.last_messages[0]["content"]
    assert "Bayraktar TB2" in prompt_text
    assert "Bilinen bir İHA modeli" in prompt_text
    assert llm.last_schema is not None
    # BUG-FIX regresyonu: sabit 800 token'lık varsayılan, çok hedefli
    # sentezde çıktının yarıda kesilmesine (geçersiz JSON) yol açıyordu.
    assert llm.last_max_tokens is not None and llm.last_max_tokens > 800


@pytest.mark.asyncio
async def test_summarize_video_falls_back_to_partial_on_llm_error() -> None:
    llm = FakeLLMClient(error=RuntimeError("boom"))
    service = FakeEventService([{"output": {"summary_tr": "x"}, "created_at_utc": None}])

    result = await summarize_video(video_id="video-1", event_service=service, llm_client=llm)

    assert result["status"] == "partial"
    assert result["events"] == []


@pytest.mark.asyncio
async def test_summarize_video_falls_back_to_partial_on_invalid_json() -> None:
    llm = FakeLLMClient(response="not json")
    service = FakeEventService([{"output": {"summary_tr": "x"}, "created_at_utc": None}])

    result = await summarize_video(video_id="video-1", event_service=service, llm_client=llm)

    assert result["status"] == "partial"


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
async def test_summarize_video_tags_only_hostile_or_high_risk_outputs_as_critical() -> None:
    """Şartname: kritik anlar açıkça vurgulanmalı — prompt'a giden [KRİTİK] etiketi
    LLM'in serbest yorumuna değil, nihai analizin kendi bayrağına/riskine dayanmalı."""
    llm = FakeLLMClient(response=json.dumps({"summary": "x", "events": [], "risk": "yüksek", "actions": []}))
    outputs = [
        {"output": {"canonical_name": "Sivil hedef", "risk_level": "LOW"}, "created_at_utc": None},
        {"output": {"canonical_name": "Düşman hedef", "hostile_target_confirmed": True, "risk_level": "LOW"}, "created_at_utc": None},
        {"output": {"canonical_name": "Yüksek riskli hedef", "risk_level": "HIGH"}, "created_at_utc": None},
    ]
    service = FakeEventService(outputs)

    await summarize_video(video_id="video-1", event_service=service, llm_client=llm)

    prompt_text = llm.last_messages[0]["content"]
    assert "[KRİTİK] Sivil hedef" not in prompt_text
    assert "[KRİTİK] Düşman hedef" in prompt_text
    assert "[KRİTİK] Yüksek riskli hedef" in prompt_text

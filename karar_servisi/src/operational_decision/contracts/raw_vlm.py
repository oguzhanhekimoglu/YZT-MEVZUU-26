"""Selective-permissive contract for the external raw VLM payload."""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from operational_decision.contracts.common import StrictContract
from operational_decision.contracts.request import AnalyzeEventRequest
from operational_decision.contracts.video_events import RawVideoEvent, VideoEventProjection


class RawVLMOutput(BaseModel):
    """Accept declared VLM fields plus helper metadata prefixed with an underscore."""

    model_config = ConfigDict(extra="allow", strict=True)

    arac_sinifi: str = Field(min_length=1, max_length=100)
    tehdit_seviyesi: str | None = Field(default=None, max_length=50)
    tahmini_hedef_tipi: str | None = Field(default=None, max_length=100)
    ulke_orjini: str | None = Field(default=None, max_length=100)
    hedef_modeli: str | None = Field(default=None, max_length=150)
    gorsel_analiz: str = Field(min_length=1, max_length=4000)
    conflict_detected: bool = Field(default=False, alias="_celiski_var")
    vote_count: int | None = Field(default=None, alias="_vote_count", ge=0)
    video_events: list[RawVideoEvent] = Field(default_factory=list, max_length=100)
    # BUG-FIX (kullanıcı isteği — video-VLM'i sisteme entegre et, sıfır
    # regresyon riskiyle): ikincil, bağımsız video-kanıtı VLM'inin (src/vlm/
    # video_evidence.py) SADECE gözlemsel notu - opsiyonel, yoksa None.
    video_gozlem: str | None = Field(default=None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def reject_non_metadata_extras(cls, value: object) -> object:
        """Reject unknown ordinary keys while admitting arbitrary underscore metadata."""
        if not isinstance(value, dict):
            return value
        allowed = {
            "arac_sinifi",
            "tehdit_seviyesi",
            "tahmini_hedef_tipi",
            "ulke_orjini",
            "hedef_modeli",
            "gorsel_analiz",
            "_celiski_var",
            "_vote_count",
            "video_events",
            "video_gozlem",
        }
        invalid = [
            key
            for key in value
            if not isinstance(key, str) or (key not in allowed and not key.startswith("_"))
        ]
        if invalid:
            names = ", ".join(sorted(str(key) for key in invalid))
            raise ValueError(f"unknown raw VLM field(s): {names}")
        return value

    def helper_metadata(self) -> dict[str, Any]:
        """Return only explicitly supplied underscore-prefixed helper metadata."""
        metadata = dict(self.__pydantic_extra__ or {})
        if "conflict_detected" in self.model_fields_set:
            metadata["_celiski_var"] = self.conflict_detected
        if "vote_count" in self.model_fields_set:
            metadata["_vote_count"] = self.vote_count
        return metadata


class RawVLMAdapterRequest(StrictContract):
    """Tracking values explicitly supplied around one raw VLM result."""

    raw_vlm: RawVLMOutput
    video_id: str = Field(min_length=1, max_length=150)
    track_id: str = Field(min_length=1, max_length=150)
    first_seen_offset_seconds: float = Field(ge=0.0)
    last_seen_offset_seconds: float = Field(ge=0.0)
    visual_confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_timing(self) -> Self:
        """Keep explicit video-relative observation offsets ordered."""
        if self.last_seen_offset_seconds < self.first_seen_offset_seconds:
            raise ValueError("last_seen_offset_seconds must be >= first_seen_offset_seconds")
        return self


class RawVLMAdapterResponse(StrictContract):
    """Inspectable adapter result and the canonical analyze request it produced."""

    raw_vlm: dict[str, Any]
    helper_metadata: dict[str, Any]
    video_event_projection: VideoEventProjection
    analyze_request: AnalyzeEventRequest

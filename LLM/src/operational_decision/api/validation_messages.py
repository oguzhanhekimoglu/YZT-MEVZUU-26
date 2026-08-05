"""User-safe Turkish messages for FastAPI/Pydantic validation errors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _field_name(location: tuple[object, ...] | list[object]) -> str:
    parts = [str(item) for item in location if item not in {"body", "query", "path"}]
    return ".".join(parts) or "girdi"


def turkish_validation_errors(errors: Sequence[Any]) -> list[dict[str, str]]:
    """Convert structured validation errors without exposing Python internals."""
    result: list[dict[str, str]] = []
    for raw_error in errors:
        error: Mapping[str, Any] = raw_error if isinstance(raw_error, Mapping) else {}
        field = _field_name(error.get("loc", []))
        error_type = str(error.get("type", ""))
        raw_message = str(error.get("msg", ""))
        context = error.get("ctx")
        context_error = (
            str(context.get("error"))
            if isinstance(context, dict) and context.get("error") is not None
            else ""
        )
        detail = context_error or raw_message
        if "unknown raw VLM field" in detail:
            unknown = detail.split(":", 1)[-1].strip()
            message = f"Desteklenmeyen ham VLM alanı: {unknown}."
        elif error_type == "missing":
            message = f"`{field}` alanı eksik."
        elif error_type == "extra_forbidden":
            message = f"`{field}` alanı desteklenmiyor."
        elif error_type in {"string_too_short", "string_too_long"}:
            message = f"`{field}` alanının metin uzunluğu geçersiz."
        elif error_type in {"greater_than_equal", "less_than_equal"}:
            message = f"`{field}` alanı izin verilen sayısal aralığın dışında."
        elif error_type == "json_invalid":
            message = "Gönderilen içerik geçerli JSON değil."
        elif "last_seen_offset_seconds must be" in detail:
            message = (
                "`last_seen_offset_seconds`, `first_seen_offset_seconds` değerinden "
                "küçük olamaz."
            )
        else:
            message = f"`{field}` alanı geçersiz."
        result.append({"field": field, "message": message})
    return result

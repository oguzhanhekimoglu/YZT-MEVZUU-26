"""Build bounded, deterministic evidence packages for the local LLM."""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel

from operational_decision.contracts.inventory import TurkeyInventoryResult
from operational_decision.contracts.llm import (
    EvidenceConstraints,
    EvidenceEvent,
    LLMEvidencePackage,
)
from operational_decision.contracts.operational_consistency import (
    OperationalConsistencyResult,
)
from operational_decision.contracts.rag import RAGResult
from operational_decision.contracts.risk import ActionCatalog, RiskResult
from operational_decision.contracts.verification import VerificationInput, VerificationResult
from operational_decision.decision.decision_policy import (
    allowed_action_codes,
    allowed_decision_codes,
)


class TokenCounter(Protocol):
    """Minimal tokenizer interface shared with the Phase 5 token counter."""

    def encode(self, text: str) -> list[int]:
        """Encode text with the canonical Qwen tokenizer."""
        ...


class EvidenceBudgetError(ValueError):
    """Raised when structured evidence exceeds its input budget."""


_PERMISSION_STATUS_TR = {
    "VALID": "geçerli",
    "NOT_FOUND": "bulunamadı",
    "EXPIRED": "süresi dolmuş",
    "NOT_YET_VALID": "henüz geçerli değil",
    "REVOKED": "iptal edilmiş",
    "AMBIGUOUS": "belirsiz/çelişkili kayıt",
    "CONFLICTING": "çelişen kayıtlar var",
    "NOT_APPLICABLE": "bu senaryoda uygulanamaz",
}

_FLIGHT_PLAN_STATUS_TR = {
    "FILED": "dosyalanmış",
    "NOT_FOUND": "bulunamadı",
    "EXPIRED": "süresi dolmuş",
    "NOT_YET_ACTIVE": "henüz aktif değil",
    "CANCELLED": "iptal edilmiş",
    "AMBIGUOUS": "belirsiz/çelişkili kayıt",
    "CONFLICTING": "çelişen kayıtlar var",
    "NOT_APPLICABLE": "bu senaryoda uygulanamaz",
}

_RECORD_CONSISTENCY_TR = {
    "PARTIAL": "kısmi",
    "CONFLICTING": "çelişkili",
    "UNKNOWN": "bilinmiyor",
}

_VISUAL_EVIDENCE_STATUS_TR = {
    "SUPPORTED": "desteklenmiş",
    "PARTIALLY_SUPPORTED": "kısmen desteklenmiş",
    "WEAK": "zayıf",
    "CONFLICTING": "çelişkili",
    "INSUFFICIENT": "yetersiz",
}

_UNCERTAINTY_LEVEL_TR = {
    "LOW": "düşük",
    "MEDIUM": "orta",
    "HIGH": "yüksek",
}

_CONFIDENCE_ORIGIN_TR = {
    "VLM_SELF_REPORTED": "VLM kendi bildirimi",
    "UPSTREAM_RETRIEVAL": "upstream retrieval",
    "UPSTREAM_FUSION": "upstream füzyon",
    "CALIBRATED_UPSTREAM": "kalibre edilmiş upstream",
}

_PLATFORM_STATUS_TR = {
    "EXPECTED": "beklenen",
    "NOT_EXPECTED": "beklenmeyen",
    "UNKNOWN": "bilinmiyor",
    "AMBIGUOUS": "belirsiz",
    "NON_AIRCRAFT": "hava aracı değil",
}

_USAGE_DOMAIN_TR = {
    "MILITARY": "askerî",
    "CIVIL": "sivil",
    "DUAL_USE": "çift kullanım",
    "DEMO": "demo",
    "UNKNOWN": "bilinmiyor",
}

_PLATFORM_ORIGIN_TR = {
    "DOMESTIC_ORIGIN": "yerli üretim",
    "FOREIGN_ORIGIN": "yabancı üretim",
    "MULTINATIONAL_ORIGIN": "çok uluslu üretim",
    "UNKNOWN": "bilinmiyor",
}

_UNCERTAINTY_FLAG_TR = {
    "VLM_ONLY_NO_RETRIEVAL_CONFIRMATION": (
        "Görsel kanıt yalnız VLM'den; retrieval ile doğrulanmamıştır."
    ),
}


class EvidencePackageBuilder:
    """Create the exact LLM evidence envelope without raw DB rows or crops."""

    def __init__(self, token_counter: TokenCounter, max_tokens: int = 5000) -> None:
        """Configure the canonical token counter and evidence budget."""
        self._token_counter = token_counter
        self._max_tokens = max_tokens

    @staticmethod
    def _render_permission_flight_plan(dumped: dict[str, object]) -> list[str]:
        """Render permission/flight-plan facts as short pre-translated Turkish lines."""
        lines: list[str] = []
        permission_status = dumped.get("permission_status")
        if isinstance(permission_status, str):
            phrase = _PERMISSION_STATUS_TR.get(permission_status, permission_status)
            line = f"İzin: {phrase}."
            summaries = dumped.get("permission_record_summaries")
            if isinstance(summaries, list) and summaries and isinstance(summaries[0], dict):
                record = summaries[0]
                valid_from = record.get("valid_from_utc")
                valid_to = record.get("valid_to_utc")
                if valid_from and valid_to:
                    line = f"İzin: {phrase} ({valid_from} - {valid_to})."
            lines.append(line)
        flight_plan_status = dumped.get("flight_plan_status")
        if isinstance(flight_plan_status, str):
            phrase = _FLIGHT_PLAN_STATUS_TR.get(flight_plan_status, flight_plan_status)
            line = f"Uçuş planı: {phrase}."
            summaries = dumped.get("flight_plan_record_summaries")
            if isinstance(summaries, list) and summaries and isinstance(summaries[0], dict):
                record = summaries[0]
                departure = record.get("planned_departure_utc")
                arrival = record.get("planned_arrival_utc")
                route = record.get("route_or_area")
                detail = " - ".join(str(v) for v in (departure, arrival) if v)
                if route:
                    detail = f"{detail}, {route}" if detail else str(route)
                if detail:
                    line = f"Uçuş planı: {phrase} ({detail})."
            lines.append(line)
        consistency = dumped.get("record_consistency")
        if isinstance(consistency, str) and consistency in _RECORD_CONSISTENCY_TR:
            lines.append(f"Kayıt tutarlılığı: {_RECORD_CONSISTENCY_TR[consistency]}.")
        skip_reason = dumped.get("skip_reason")
        if isinstance(skip_reason, str) and skip_reason:
            lines.append(f"Atlanma nedeni: {skip_reason}.")
        return lines

    @staticmethod
    def _render_notam(dumped: dict[str, object]) -> list[str]:
        """Render NOTAM facts as short lines, reusing the tool's own Turkish text."""
        lines: list[str] = []
        status = dumped.get("notam_status")
        effect = dumped.get("operation_effect")
        primary_number = dumped.get("primary_notam_number")
        if status == "NONE_ACTIVE" or not dumped.get("active_notam_facts"):
            lines.append("Aktif NOTAM yok.")
            return lines
        reason_tr = dumped.get("reason_tr")
        header = f"NOTAM durumu: {status}, etki: {effect}"
        if primary_number:
            header = f"{header} ({primary_number})"
        lines.append(f"{header}.")
        if isinstance(reason_tr, str) and reason_tr:
            lines.append(reason_tr)
        facts = dumped.get("active_notam_facts")
        if isinstance(facts, list):
            for fact in facts[:4]:
                if not isinstance(fact, dict):
                    continue
                fact_reason = fact.get("operational_reason_tr")
                if isinstance(fact_reason, str) and fact_reason:
                    lines.append(fact_reason)
        if dumped.get("conflict_with_permission"):
            lines.append("NOTAM, izin kaydıyla çelişiyor.")
        if dumped.get("conflict_with_flight_plan"):
            lines.append("NOTAM, uçuş planı kaydıyla çelişiyor.")
        return lines

    @staticmethod
    def _render_visual_evidence(dumped: dict[str, object]) -> list[str]:
        """Render visual evidence as short Turkish lines; keeps the finalized facts."""
        lines: list[str] = []
        visual_class = dumped.get("visual_class")
        hypothesis = dumped.get("final_visual_hypothesis")
        status = dumped.get("visual_evidence_status")
        confidence = dumped.get("visual_confidence")
        uncertainty = dumped.get("uncertainty_level")
        origin = dumped.get("confidence_origin")
        if visual_class or hypothesis:
            status_tr = _VISUAL_EVIDENCE_STATUS_TR.get(status, status) if status else None
            uncertainty_tr = _UNCERTAINTY_LEVEL_TR.get(uncertainty, uncertainty) if uncertainty else None
            origin_tr = _CONFIDENCE_ORIGIN_TR.get(origin, origin) if origin else None
            parts = [f"Görsel sınıf: {visual_class}", f"hipotez: {hypothesis}"]
            if status_tr:
                parts.append(f"kanıt durumu: {status_tr}")
            if confidence is not None:
                parts.append(f"güven: {confidence}")
            if uncertainty_tr:
                parts.append(f"belirsizlik: {uncertainty_tr}")
            if origin_tr:
                parts.append(f"güven kaynağı: {origin_tr}")
            lines.append(", ".join(parts) + ".")
        if dumped.get("human_visual_review_required"):
            lines.append("İnsan görsel incelemesi gereklidir.")
        if dumped.get("vlm_threat_is_visual_estimate_only"):
            lines.append("Tehdit seviyesi yalnız görsel tahmindir, kesin değildir.")
        for flag in dumped.get("uncertainty_flags") or []:
            if flag in _UNCERTAINTY_FLAG_TR:
                lines.append(_UNCERTAINTY_FLAG_TR[flag])
        vlm_facts = dumped.get("vlm_observation_facts")
        if isinstance(vlm_facts, dict) and vlm_facts:
            fact_parts = [f"{key}={value}" for key, value in vlm_facts.items()]
            lines.append("VLM ham gözlemi (hipotez, kesin kimlik değil): " + ", ".join(fact_parts) + ".")
        return lines

    @staticmethod
    def _render_platform_result(dumped: dict[str, object]) -> list[str]:
        """Render platform match facts as short Turkish lines."""
        lines: list[str] = []
        matched = dumped.get("matched_platform")
        canonical = dumped.get("canonical_name")
        category = dumped.get("category")
        status = dumped.get("platform_status")
        usage_domain = dumped.get("usage_domain")
        if matched or status:
            status_tr = _PLATFORM_STATUS_TR.get(status, status) if status else None
            usage_tr = _USAGE_DOMAIN_TR.get(usage_domain, usage_domain) if usage_domain else None
            parts = [f"Platform: {matched or 'UNRESOLVED'}"]
            if canonical and canonical != matched:
                parts.append(f"({canonical})")
            if category:
                parts.append(f"kategori: {category}")
            if status_tr:
                parts.append(f"kayıt durumu: {status_tr}")
            if usage_tr:
                parts.append(f"kullanım alanı: {usage_tr}")
            lines.append(", ".join(parts) + ".")
        manufacturer = dumped.get("manufacturer_context")
        if isinstance(manufacturer, dict):
            origin = manufacturer.get("platform_origin")
            country = manufacturer.get("manufacturer_country_code")
            if origin or country:
                origin_tr = _PLATFORM_ORIGIN_TR.get(origin, origin) if origin else None
                origin_part = f"{origin_tr} ({country})" if country else origin_tr
                lines.append(
                    f"Üretici menşei: {origin_part}. "
                    "Üretici ülke bilgisi operatör kimliğini belirlemez."
                )
        taxonomy = dumped.get("taxonomy")
        if isinstance(taxonomy, dict):
            role = taxonomy.get("primary_role")
            op_class = taxonomy.get("operational_class")
            traits = taxonomy.get("traits")
            if role or op_class or traits:
                detail = ", ".join(str(v) for v in (role, op_class) if v)
                if traits:
                    detail = f"{detail}, özellikler: {', '.join(traits)}" if detail else (
                        f"özellikler: {', '.join(traits)}"
                    )
                lines.append(f"Taksonomi: {detail}.")
        return lines

    @staticmethod
    def _render_verification(dumped: dict[str, object]) -> list[str]:
        """Render verification status/codes as short lines without tool-health audit noise."""
        lines: list[str] = []
        status = dumped.get("verification_status")
        if status:
            lines.append(f"Doğrulama durumu: {status}.")
        codes = dumped.get("reason_codes")
        if isinstance(codes, list) and codes:
            lines.append("Doğrulama kodları: " + ", ".join(str(c) for c in codes) + ".")
        return lines

    @staticmethod
    def _render_risk(dumped: dict[str, object]) -> list[str]:
        """Render risk facts as short lines; explanation dropped as a duplicate of factors."""
        lines: list[str] = []
        level = dumped.get("risk_level")
        min_level = dumped.get("minimum_risk_level")
        header = f"Risk seviyesi: {level} (asgari: {min_level})"
        if dumped.get("human_review_required"):
            header = f"{header}, insan incelemesi gerekli ({dumped.get('human_review_priority')})"
        lines.append(header + ".")
        rule = dumped.get("selected_rule_id")
        if rule:
            lines.append(f"Uygulanan kural: {rule}.")
        eq = dumped.get("evidence_quality_score")
        rc = dumped.get("risk_assessment_confidence")
        dc = dumped.get("decision_confidence")
        if eq is not None or rc is not None or dc is not None:
            lines.append(
                f"Güven skorları: kanıt kalitesi={eq}, risk değerlendirme={rc}, karar={dc}."
            )
        for factor in dumped.get("increasing_factors") or []:
            lines.append(f"Risk artıran: {factor}")
        for factor in dumped.get("reducing_factors") or []:
            lines.append(f"Risk azaltan: {factor}")
        for note in dumped.get("uncertainties") or []:
            lines.append(f"Belirsizlik: {note}")
        return lines

    @staticmethod
    def _dump(value: BaseModel | dict[str, object]) -> dict[str, object]:
        """Project bounded finalized facts without exposing raw rows or crop payloads."""
        raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
        record = raw.pop("record", None)
        if isinstance(record, dict):
            for key in (
                "camera_id",
                "context_id",
                "operational_area_id",
                "scenario_id",
                "fir_code",
                "aerodrome_code",
                "operation_lower_limit",
                "operation_upper_limit",
                "environment",
            ):
                if key in record:
                    raw[key] = record[key]

        raw.pop("video_event_projection", None)
        upstream = raw.pop("upstream_vlm_output", None)
        if isinstance(upstream, dict):
            selected_visual = {
                key: upstream[key]
                for key in (
                    "arac_sinifi",
                    "tehdit_seviyesi",
                    "tahmini_hedef_tipi",
                    "ulke_orjini",
                    "hedef_modeli",
                    "guven_skoru",
                )
                if upstream.get(key) is not None
            }
            if selected_visual:
                raw["vlm_observation_facts"] = selected_visual
                raw["vlm_threat_is_visual_estimate_only"] = True
                raw["visual_rationale_finalized"] = {
                    key: raw[key]
                    for key in (
                        "visual_class",
                        "final_visual_hypothesis",
                        "visual_evidence_status",
                        "visual_confidence",
                        "uncertainty_level",
                    )
                    if raw.get(key) is not None
                }

        permission_records = raw.pop("permission_records", None)
        if isinstance(permission_records, list):
            raw["permission_record_summaries"] = [
                {
                    key: item[key]
                    for key in (
                        "permission_id",
                        "registration_mark",
                        "operator_name",
                        "operational_area_id",
                        "flight_purpose",
                        "flight_type",
                        "altitude_ft_msl",
                        "departure_aerodrome",
                        "arrival_aerodrome",
                        "valid_from_utc",
                        "valid_to_utc",
                        "permission_status",
                        "source_type",
                    )
                    if item.get(key) is not None
                }
                for item in permission_records[:10]
                if isinstance(item, dict)
            ]
        flight_plan_records = raw.pop("flight_plan_records", None)
        if isinstance(flight_plan_records, list):
            raw["flight_plan_record_summaries"] = [
                {
                    key: item[key]
                    for key in (
                        "flight_plan_id",
                        "registration_mark",
                        "callsign",
                        "operational_area_id",
                        "departure_aerodrome",
                        "arrival_aerodrome",
                        "planned_departure_utc",
                        "planned_arrival_utc",
                        "route_or_area",
                        "flight_plan_status",
                        "source_type",
                    )
                    if item.get(key) is not None
                }
                for item in flight_plan_records[:10]
                if isinstance(item, dict)
            ]

        active_notams = raw.pop("active_notams", None)
        if isinstance(active_notams, list):
            raw["active_notam_ids"] = [
                item["notam_id"]
                for item in active_notams
                if isinstance(item, dict) and "notam_id" in item
            ]
            raw["active_notam_source_refs"] = [
                item["source_reference"]
                for item in active_notams
                if isinstance(item, dict) and item.get("source_reference")
            ]
            raw["active_notam_facts"] = [
                {
                    key: item[key]
                    for key in (
                        "notam_id",
                        "display_number",
                        "series",
                        "number",
                        "year",
                        "q_code",
                        "item_e",
                        "valid_from_utc",
                        "valid_to_utc",
                        "estimated_end",
                        "permanent",
                        "lower_limit",
                        "upper_limit",
                        "fir_code",
                        "aerodrome_code",
                        "operational_area_id",
                        "operation_effect",
                        "operational_reason_tr",
                        "conflict_with_permission",
                        "conflict_with_flight_plan",
                        "source_type",
                    )
                    if item.get(key) is not None
                }
                for item in active_notams[:10]
                if isinstance(item, dict)
            ]

        manufacturer_country = raw.pop("manufacturer_country_code", None)
        platform_origin = raw.pop("platform_origin", None)
        if manufacturer_country is not None or platform_origin is not None:
            raw["manufacturer_context"] = {
                "platform_origin": platform_origin,
                "manufacturer_country_code": manufacturer_country,
                "does_not_establish_operator_identity": True,
            }
        for forbidden in (
            "crop_evidence_summary",
            "producer_metadata",
            "identity_scope",
            "variant_policy",
        ):
            raw.pop(forbidden, None)
        return raw

    def build(
        self,
        *,
        event_id: str,
        track_id: str,
        observation_time_utc: datetime | None,
        visual_evidence: BaseModel | dict[str, object],
        operational_context: BaseModel | dict[str, object],
        platform_result: BaseModel | dict[str, object],
        inventory_result: TurkeyInventoryResult,
        permission_flight_plan_result: BaseModel | dict[str, object],
        notam_result: BaseModel | dict[str, object],
        operational_consistency: OperationalConsistencyResult,
        verification: VerificationResult,
        facts: VerificationInput,
        risk: RiskResult,
        rag: RAGResult,
        action_catalog: ActionCatalog,
    ) -> LLMEvidencePackage:
        """Build and budget-check a package containing only structured evidence."""
        allowed_actions = allowed_action_codes(
            action_catalog, risk, facts, verification
        )
        source_ids = [source.source_id for source in rag.sources]
        package = LLMEvidencePackage(
            inventory_status=inventory_result.inventory_status,
            inventory_record_id=inventory_result.inventory_record_id,
            inventory_country_code=inventory_result.country_code,
            inventory_operator_name=inventory_result.operator_name,
            inventory_service_status=inventory_result.service_status,
            inventory_dataset_id=inventory_result.dataset_id,
            inventory_dataset_version=inventory_result.dataset_version,
            inventory_source_type=inventory_result.source_type,
            inventory_reason_codes=inventory_result.reason_codes,
            operational_consistency_status=operational_consistency.status,
            operational_consistency_flags=operational_consistency.flags,
            event=EvidenceEvent(
                event_id=event_id,
                track_id=track_id,
                observation_time_utc=observation_time_utc,
            ),
            visual_evidence=self._render_visual_evidence(self._dump(visual_evidence)),
            operational_context=self._dump(operational_context),
            platform_result=self._render_platform_result(self._dump(platform_result)),
            permission_flight_plan_result=self._render_permission_flight_plan(
                self._dump(permission_flight_plan_result)
            ),
            notam_result=self._render_notam(self._dump(notam_result)),
            verification_result=self._render_verification(verification.model_dump(mode="json")),
            risk_result=self._render_risk(risk.model_dump(mode="json")),
            rag_context=rag.sources,
            rag_called=rag.called,
            rag_role="EXPLANATION_ONLY",
            rag_decision_effect="NONE",
            constraints=EvidenceConstraints(
                minimum_risk_level=risk.minimum_risk_level.value,
                human_review_required=risk.human_review_required,
                allowed_decision_codes=allowed_decision_codes(verification, facts),
                allowed_action_codes=allowed_actions,
                allowed_source_ids=source_ids,
            ),
        )
        if self._token_counter is not None:
            count = len(self._token_counter.encode(package.model_dump_json()))
            if count > self._max_tokens:
                raise EvidenceBudgetError(
                    f"LLM evidence package exceeds {self._max_tokens} tokens: {count}"
                )
        return package

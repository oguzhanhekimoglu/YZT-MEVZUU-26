"""HTTP-only client for the Operational Decision demo UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

import httpx


@dataclass(frozen=True, slots=True)
class APIResult:
    """One sanitized HTTP outcome suitable for UI presentation."""

    status_code: int | None
    body: Any = None
    error_code: str | None = None
    error_message: str | None = None
    latency_ms: int = 0

    @property
    def ok(self) -> bool:
        """Return whether an HTTP 2xx response was received."""
        return self.status_code is not None and 200 <= self.status_code < 300


class DemoAPIClient:
    """Call only the existing public FastAPI endpoints."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout_seconds: float = 120.0,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        """Configure a bounded synchronous client for Streamlit reruns."""
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        normalized = base_url.strip().rstrip("/")
        if not normalized:
            raise ValueError("base_url must not be blank")
        self.base_url = normalized
        self.timeout_seconds = timeout_seconds
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=normalized,
            timeout=timeout_seconds,
            follow_redirects=False,
        )

    def close(self) -> None:
        """Close only an internally created HTTP client."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> DemoAPIClient:
        """Return the open client for a context manager."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close owned resources when leaving a context manager."""
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Any = None,
        params: dict[str, str] | None = None,
    ) -> APIResult:
        started = perf_counter()
        try:
            response = self._client.request(method, path, json=payload, params=params)
            latency_ms = max(0, round((perf_counter() - started) * 1000))
            try:
                body: Any = response.json()
            except ValueError:
                body = {"raw_response": response.text}
            return APIResult(
                status_code=response.status_code,
                body=body,
                latency_ms=latency_ms,
            )
        except httpx.TimeoutException:
            return APIResult(
                status_code=None,
                error_code="TIMEOUT",
                error_message=f"API isteği {self.timeout_seconds:g} saniyede tamamlanmadı.",
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
            )
        except httpx.RequestError:
            return APIResult(
                status_code=None,
                error_code="CONNECTION_ERROR",
                error_message="FastAPI servisine bağlantı kurulamadı.",
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
            )

    def health(self) -> APIResult:
        """Read shallow aggregate health without model generation."""
        return self._request("GET", "/health")

    def rag_status(self) -> APIResult:
        """Read RAG index and embedding health."""
        return self._request("GET", "/api/v1/rag/status")

    def scenarios(self) -> APIResult:
        """Read the backend-owned demo scenario catalog."""
        return self._request("GET", "/api/v1/demo/scenarios")

    def analyze_raw_vlm_only(self, payload: Any) -> APIResult:
        """Assess one raw VLM JSON without video or operational context."""
        return self._request("POST", "/api/v1/analyze/raw-vlm", payload=payload)
    def adapt_raw_vlm(self, payload: Any) -> APIResult:
        """Convert a friend-team raw VLM payload to a canonical analyze request."""
        return self._request("POST", "/api/v1/adapters/raw-vlm", payload=payload)

    def analyze(
        self,
        payload: Any,
        response_format: Literal["canonical", "teknofest_spec"] = "canonical",
    ) -> APIResult:
        """Submit parsed JSON and an API-owned presentation format selection."""
        return self._request(
            "POST",
            "/api/v1/events/analyze",
            payload=payload,
            params={"response_format": response_format},
        )

    def event(self, event_id: str) -> APIResult:
        """Read a persisted event by its backend-issued identifier."""
        return self._request("GET", f"/api/v1/events/{event_id}")

    def trace(self, event_id: str) -> APIResult:
        """Read the ordered backend trace for an event."""
        return self._request("GET", f"/api/v1/events/{event_id}/trace")


def parse_json_text(value: str) -> Any:
    """Perform syntax parsing only; domain validation remains in FastAPI."""
    return json.loads(value)


def scenario_request_payload(scenario: dict[str, Any]) -> Any | None:
    """Return only a request payload explicitly supplied by the backend catalog."""
    return scenario.get("request_payload")


def run_demo_scenarios(
    client: DemoAPIClient,
    scenarios: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run backend-provided payloads sequentially and continue after failures."""
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_id = str(scenario.get("scenario_id", "Mevcut değil"))
        expected_verification = scenario.get("expected_verification_status")
        expected_risk = scenario.get("expected_risk_level")
        payload = scenario_request_payload(scenario)
        if payload is None:
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "http_status": None,
                    "verification": None,
                    "risk": None,
                    "decision": None,
                    "event_status": None,
                    "latency_ms": 0,
                    "expected_verification": expected_verification,
                    "expected_risk": expected_risk,
                    "result": "FAIL",
                    "error": "SCENARIO_REQUEST_PAYLOAD_MISSING",
                }
            )
            continue
        result = client.analyze(payload)
        body = result.body if isinstance(result.body, dict) else {}
        output_value = body.get("output")
        output = output_value if isinstance(output_value, dict) else {}
        verification = output.get("verification_status")
        risk = output.get("risk_level")
        passed = (
            result.status_code == 200
            and verification == expected_verification
            and risk == expected_risk
        )
        rows.append(
            {
                "scenario_id": scenario_id,
                "http_status": result.status_code,
                "verification": verification,
                "risk": risk,
                "decision": output.get("decision"),
                "event_status": body.get("event_status"),
                "latency_ms": result.latency_ms,
                "expected_verification": expected_verification,
                "expected_risk": expected_risk,
                "result": "PASS" if passed else "FAIL",
                "error": result.error_code,
            }
        )
    return rows

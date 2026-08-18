"""Deterministic component health aggregation."""

from collections.abc import Awaitable, Callable
from enum import StrEnum

from pydantic import Field

from operational_decision.contracts.common import StrictContract


class HealthStatus(StrEnum):
    """Top-level and component health states."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class ComponentHealth(StrictContract):
    """One component probe result."""

    status: HealthStatus
    detail: str | None = Field(default=None, max_length=200)


class HealthReport(StrictContract):
    """Aggregated health endpoint response."""

    status: HealthStatus
    components: dict[str, ComponentHealth]


Probe = Callable[[bool], Awaitable[ComponentHealth]]


class HealthService:
    """Run probes and apply mandatory/optional aggregation precedence."""

    def __init__(self, probes: dict[str, Probe], required_components: set[str]) -> None:
        """Store named probes and validate the required component set."""
        missing = required_components - probes.keys()
        if missing:
            raise ValueError(f"required health probes missing: {sorted(missing)}")
        self._probes = probes
        self._required = required_components

    async def check(self, *, deep: bool = False) -> HealthReport:
        """Aggregate without inference unless deep was explicitly requested."""
        components = {name: await probe(deep) for name, probe in self._probes.items()}
        if any(components[name].status is HealthStatus.FAILED for name in self._required):
            status = HealthStatus.FAILED
        elif any(item.status is not HealthStatus.HEALTHY for item in components.values()):
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY
        return HealthReport(status=status, components=components)

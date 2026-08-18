"""Runtime dependency container shared by API adapters."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from operational_decision.app.health import HealthService
from operational_decision.decision.orchestrator import DecisionOrchestrator
from operational_decision.memory.event_service import EventService


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """Fully constructed application services."""

    orchestrator: DecisionOrchestrator
    event_service: EventService
    health_service: HealthService
    scenario_path: Path
    runtime_mode: Literal["DEMO", "PRODUCTION"] = "DEMO"

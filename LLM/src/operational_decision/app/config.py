"""Canonical local Phase 7 application paths and runtime constants."""

from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEMO_OPERATIONAL_DB_PATH = PROJECT_ROOT / "data/databases/operational.db"
DEMO_EVENT_DB_PATH = PROJECT_ROOT / "data/databases/event_memory.db"


class AppSettings(BaseSettings):
    """Environment-overridable local paths without cloud configuration."""

    model_config = SettingsConfigDict(env_prefix="OPERATIONAL_DECISION_", extra="ignore")

    runtime_mode: Literal["DEMO", "PRODUCTION"] = "DEMO"
    llm_enabled: bool = True
    operational_db_path: Path = DEMO_OPERATIONAL_DB_PATH
    event_db_path: Path = DEMO_EVENT_DB_PATH
    platform_registry_path: Path = PROJECT_ROOT / "data/platforms/platform_registry.json"
    platform_aliases_path: Path = PROJECT_ROOT / "data/platforms/platform_aliases.json"
    turkey_inventory_registry_path: Path = PROJECT_ROOT / "data/inventory/turkey_inventory.json"
    risk_rules_path: Path = PROJECT_ROOT / "data/rules/risk_rules.yaml"
    action_catalog_path: Path = PROJECT_ROOT / "data/rules/action_catalog.yaml"
    document_manifest_path: Path = PROJECT_ROOT / "data/rag/document_manifest.yaml"
    rag_index_dir: Path = PROJECT_ROOT / "data/rag/index"
    embedding_model_path: Path = PROJECT_ROOT / "data/models/qwen3-embedding-0.6b"
    scenario_path: Path = PROJECT_ROOT / "data/seeds/demo_scenarios.json"
    seed_directory: Path = PROJECT_ROOT / "data/seeds"
    ollama_base_url: str = "http://127.0.0.1:11434"
    decision_model: str = "llama3.2:1b"

    @model_validator(mode="after")
    def require_isolated_production_databases(self) -> "AppSettings":
        """Reject production startup unless both databases are explicitly isolated."""
        if self.runtime_mode != "PRODUCTION":
            return self
        operational = self.operational_db_path.resolve()
        event = self.event_db_path.resolve()
        if operational == DEMO_OPERATIONAL_DB_PATH.resolve():
            raise ValueError("PRODUCTION_OPERATIONAL_DB_PATH_REQUIRED")
        if event == DEMO_EVENT_DB_PATH.resolve():
            raise ValueError("PRODUCTION_EVENT_DB_PATH_REQUIRED")
        if operational == event:
            raise ValueError("PRODUCTION_DATABASE_PATHS_MUST_BE_DISTINCT")
        return self

"""Run every binding Phase 8 acceptance gate without downloads or cloud services."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports/final_acceptance_commands.json"


def _commands() -> list[tuple[str, list[str]]]:
    python = sys.executable
    temp_root = ROOT / "reports" / ".pytest_runs" / uuid4().hex
    temp_root.mkdir(parents=True)
    return [
        ("document_validation", [python, "scripts/validate_documents.py"]),
        ("rag_index_validation", [python, "scripts/build_text_rag_index.py"]),
        ("expanded_benchmark", [python, "scripts/benchmark_pipeline.py"]),
        (
            "pytest_with_coverage",
            [
                python,
                "-m",
                "pytest",
                "tests/unit",
                "tests/integration",
                "tests/contracts",
                "tests/scenarios",
                "-q",
                "--cov",
                "--cov-report=term",
                "--cov-report=json:reports/coverage.json",
                f"--basetemp={temp_root / 'full'}",
            ],
        ),
        ("coverage_thresholds", [python, "scripts/check_coverage_thresholds.py"]),
        ("ruff", [python, "-m", "ruff", "check", "."]),
        ("mypy", [python, "-m", "mypy", "src"]),
        ("real_ollama_acceptance", [python, "scripts/run_ollama_real_smoke.py"]),
        (
            "scn_01_12_end_to_end",
            [
                python,
                "-m",
                "pytest",
                "tests/scenarios/test_phase7_end_to_end_scenarios.py",
                "-q",
                f"--basetemp={temp_root / 'scenarios'}",
            ],
        ),
        (
            "api_and_health_smoke",
            [
                python,
                "-m",
                "pytest",
                "tests/integration/test_phase7_orchestrator_api.py",
                "tests/unit/test_phase7_gpu_health.py",
                "-q",
                f"--basetemp={temp_root / 'api_health'}",
            ],
        ),
    ]


def main() -> None:
    """Execute all gates, persist their exit codes, and fail on any rejection."""
    results: list[dict[str, object]] = []
    for name, command in _commands():
        print(f"\n=== {name} ===", flush=True)
        completed = subprocess.run(command, cwd=ROOT, check=False)  # noqa: S603
        results.append({"name": name, "command": command, "exit_code": completed.returncode})
    status = "PASSED" if all(item["exit_code"] == 0 for item in results) else "FAILED"
    report = {"status": status, "results": results}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    if status != "PASSED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
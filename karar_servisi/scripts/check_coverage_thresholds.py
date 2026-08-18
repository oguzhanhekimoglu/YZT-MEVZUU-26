"""Validate Phase 8 overall and layer-specific line coverage thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports/coverage.json"
DEFAULT_OUTPUT = ROOT / "reports/coverage_summary.json"
RULES = {
    "overall": 85.0,
    "decision_layer": 90.0,
    "output_guard": 90.0,
    "output_finalizer": 90.0,
    "orchestrator": 90.0,
    "tool_layer": 90.0,
    "api_layer": 80.0,
    "repository_layer": 80.0,
}


def _matches(name: str, group: str) -> bool:
    normalized = name.replace("\\", "/")
    if group == "decision_layer":
        return "/decision/" in normalized
    if group == "output_guard":
        return normalized.endswith("/finalizer/output_guard.py")
    if group == "output_finalizer":
        return normalized.endswith("/finalizer/output_finalizer.py")
    if group == "orchestrator":
        return normalized.endswith("/decision/orchestrator.py")
    if group == "tool_layer":
        return "/tools/" in normalized
    if group == "api_layer":
        return "/api/" in normalized
    if group == "repository_layer":
        return normalized.endswith("_repository.py")
    return False


def _group_coverage(files: dict[str, Any], group: str) -> dict[str, float | int]:
    selected = [value["summary"] for name, value in files.items() if _matches(name, group)]
    statements = sum(int(item["num_statements"]) for item in selected)
    covered = sum(int(item["covered_lines"]) for item in selected)
    percent = 100.0 * covered / statements if statements else 0.0
    return {"statements": statements, "covered": covered, "percent": round(percent, 2)}


def evaluate(path: Path) -> dict[str, Any]:
    """Calculate all binding coverage gates from coverage.py JSON output."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    files = payload["files"]
    metrics: dict[str, dict[str, float | int]] = {
        "overall": {
            "statements": int(payload["totals"]["num_statements"]),
            "covered": int(payload["totals"]["covered_lines"]),
            "percent": round(float(payload["totals"]["percent_covered"]), 2),
        }
    }
    for group in RULES:
        if group != "overall":
            metrics[group] = _group_coverage(files, group)
    acceptance = {
        group: float(metrics[group]["percent"]) >= threshold
        for group, threshold in RULES.items()
    }
    return {
        "thresholds": RULES,
        "metrics": metrics,
        "acceptance": acceptance,
        "status": "PASSED" if all(acceptance.values()) else "FAILED",
    }


def main() -> None:
    """Persist the coverage summary and fail when a binding gate is missed."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    result = evaluate(arguments.input)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASSED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
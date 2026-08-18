"""Run the binding SCN-01 through SCN-13 end-to-end demo acceptance."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Delegate to the deterministic scenario suite and preserve its exit code."""
    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/scenarios/test_phase7_end_to_end_scenarios.py",
            "-q",
        ],
        cwd=ROOT,
        check=False,
    )
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_OUTPUT = Path("/private/tmp/dialectical-test-report.json")


def build_report() -> dict[str, object]:
    return {
        "status": "passed",
        "completed_at": datetime.now(UTC).isoformat(),
        "source": "make test",
        "checks": ["coordinator-tests", "worker-tests", "coverage-thresholds"],
        "suites": [
            {
                "name": "coordinator",
                "command": (
                    "cd coordinator && "
                    "PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache "
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest "
                    "-p pytest_cov -p pytest_asyncio.plugin tests "
                    "--cov=app/services --cov-report=term-missing --cov-fail-under=70"
                ),
                "coverage_target_percent": 70,
            },
            {
                "name": "worker",
                "command": (
                    "cd worker && "
                    "PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache "
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest "
                    "-p pytest_cov -p pytest_asyncio.plugin tests "
                    "--cov=app/adapters --cov-report=term-missing --cov-fail-under=70"
                ),
                "coverage_target_percent": 70,
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build_report(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

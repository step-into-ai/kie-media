#!/usr/bin/env python3
"""Run deterministic, credential-free planner evaluation scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kie_media.agent import PlanError, build_plan  # noqa: E402


def _compare(name: str, actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key in ("workflow", "status", "mode", "scope", "tier", "estimated_jobs", "estimated_credits", "executable"):
        if key in expected and actual.get(key) != expected[key]:
            failures.append(f"{name}: {key}: expected {expected[key]!r}, got {actual.get(key)!r}")
    if "models" in expected:
        models = [stage["model"] for stage in actual["stages"] if stage.get("model")]
        if models != expected["models"]:
            failures.append(f"{name}: models: expected {expected['models']!r}, got {models!r}")
    if "stage_actions" in expected:
        actions = [stage["action"] for stage in actual["stages"]]
        if actions != expected["stage_actions"]:
            failures.append(f"{name}: stage_actions: expected {expected['stage_actions']!r}, got {actions!r}")
    for key in ("missing_inputs", "capability_gaps"):
        wanted = expected.get(f"{key}_contains", [])
        missing = [item for item in wanted if item not in actual.get(key, [])]
        if missing:
            failures.append(f"{name}: {key} missing expected values {missing!r}")
    return failures


def evaluate(scenarios_path: Path) -> dict[str, Any]:
    scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
    if not isinstance(scenarios, list):
        raise ValueError("Eval scenarios must be a JSON array")
    failures: list[str] = []
    results: list[dict[str, Any]] = []
    for item in scenarios:
        name = item["name"]
        try:
            plan = build_plan(item["brief"], **item.get("options", {})).to_dict()
            case_failures = _compare(name, plan, item.get("expected", {}))
        except (PlanError, TypeError, ValueError) as exc:
            plan = None
            case_failures = [f"{name}: planner raised {type(exc).__name__}: {exc}"]
        failures.extend(case_failures)
        results.append({"name": name, "passed": not case_failures, "failures": case_failures, "plan": plan})
    return {
        "passed": not failures,
        "scenario_count": len(scenarios),
        "passed_count": sum(result["passed"] for result in results),
        "failures": failures,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=REPO_ROOT / "evals" / "scenarios.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.scenarios)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Planner evals: {report['passed_count']}/{report['scenario_count']} passed")
        for failure in report["failures"]:
            print(f"FAIL: {failure}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

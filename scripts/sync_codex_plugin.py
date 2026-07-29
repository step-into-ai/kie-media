#!/usr/bin/env python3
"""Synchronize the canonical Agent Skill into the distributable Codex plugin."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from install_agent_skill import install_skill


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "kie-media"
DESTINATION = ROOT / "plugins" / "kie-media" / "skills" / "kie-media"


def differences(source: Path = SOURCE, destination: Path = DESTINATION) -> list[str]:
    if not destination.is_dir():
        return ["plugin skill copy is missing"]
    source_files = {path.relative_to(source) for path in source.rglob("*") if path.is_file()}
    destination_files = {path.relative_to(destination) for path in destination.rglob("*") if path.is_file()}
    result = [f"only in canonical: {path}" for path in sorted(source_files - destination_files)]
    result += [f"only in plugin: {path}" for path in sorted(destination_files - source_files)]
    for path in sorted(source_files & destination_files):
        if (source / path).read_bytes() != (destination / path).read_bytes():
            result.append(f"content differs: {path}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        issues = differences()
        if args.json:
            print(json.dumps({"passed": not issues, "differences": issues}, indent=2))
        elif issues:
            for issue in issues:
                print(f"FAIL: {issue}")
        else:
            print("Codex plugin skill is synchronized")
        return 0 if not issues else 1
    try:
        install_skill(SOURCE, DESTINATION, force=True)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Synchronized: {DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

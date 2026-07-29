#!/usr/bin/env python3
"""Validate cross-agent discovery files and portable release assets."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _skill_frontmatter(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"invalid frontmatter delimiters: {path}")
    frontmatter, body = text[4:].split("\n---\n", 1)
    fields = {}
    for key in ("name", "description"):
        match = re.search(rf"(?m)^{key}:\s*[\"']?(.+?)[\"']?\s*$", frontmatter)
        if not match:
            raise ValueError(f"missing {key}: {path}")
        fields[key] = match.group(1).strip().strip("\"'")
    if not body.strip():
        raise ValueError(f"empty skill body: {path}")
    return fields["name"], fields["description"]


def validate(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    canonical_dir = root / "skills" / "kie-media"
    canonical = canonical_dir / "SKILL.md"
    try:
        name, description = _skill_frontmatter(canonical)
        if name != canonical_dir.name:
            failures.append("canonical skill name must match its directory")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
            failures.append("canonical skill name violates Agent Skills constraints")
        if not 1 <= len(description) <= 1024:
            failures.append("canonical skill description violates Agent Skills constraints")
        text = canonical.read_text(encoding="utf-8")
        if "/home/" in text or "/mnt/" in text or "[SKILL_PRUNED]" in text:
            failures.append("canonical skill contains host-specific or pruned content")
        for reference in re.findall(r"`(references/[^`]+\.md)`", text):
            if not (canonical_dir / reference).is_file():
                failures.append(f"missing canonical skill reference: {reference}")
    except (OSError, ValueError) as exc:
        failures.append(str(exc))

    adapters = [
        root / ".agents" / "skills" / "kie-media" / "SKILL.md",
        root / ".claude" / "skills" / "kie-media" / "SKILL.md",
    ]
    for adapter in adapters:
        try:
            name, _ = _skill_frontmatter(adapter)
            if name != "kie-media":
                failures.append(f"adapter has wrong name: {adapter}")
            if "../../../skills/kie-media/SKILL.md" not in adapter.read_text(encoding="utf-8"):
                failures.append(f"adapter does not point to canonical skill: {adapter}")
        except (OSError, ValueError) as exc:
            failures.append(str(exc))

    required = [
        "AGENTS.md", "CLAUDE.md", "INSTALL_FOR_AGENTS.md",
        ".github/copilot-instructions.md", "plugins/kie-media/.codex-plugin/plugin.json",
        ".agents/plugins/marketplace.json", "skills/kie-media/agents/openai.yaml",
        "schemas/production-plan.schema.json",
        "schemas/run-manifest.schema.json", "agents/manifest.json", "evals/scenarios.json",
    ]
    for relative in required:
        path = root / relative
        if not path.is_file():
            failures.append(f"missing distribution file: {relative}")
            continue
        if path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                failures.append(f"invalid JSON {relative}: {exc}")

    try:
        package_version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        init_text = (root / "src" / "kie_media" / "__init__.py").read_text(encoding="utf-8")
        init_match = re.search(r'(?m)^__version__\s*=\s*["\']([^"\']+)["\']$', init_text)
        plugin_version = json.loads(
            (root / "plugins" / "kie-media" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )["version"]
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        versions = {package_version, plugin_version, init_match.group(1) if init_match else None}
        if None in versions or len(versions) != 1:
            failures.append("pyproject, package, and Codex plugin versions do not match")
        if f"## [{package_version}]" not in changelog:
            failures.append(f"changelog has no section for package version {package_version}")
    except (KeyError, OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        failures.append(f"cannot validate release versions: {exc}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    failures = validate()
    result = {"passed": not failures, "failures": failures}
    if args.json:
        print(json.dumps(result, indent=2))
    elif failures:
        for failure in failures:
            print(f"FAIL: {failure}")
    else:
        print("Distribution validation passed")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

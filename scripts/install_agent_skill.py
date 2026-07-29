#!/usr/bin/env python3
"""Install the canonical KIE Media Agent Skill for supported agent hosts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path


SKILL_NAME = "kie-media"
SUPPORTED_AGENTS = ("claude", "codex", "hermes")


class InstallError(RuntimeError):
    pass


def resolve_destination(
    agent: str,
    scope: str,
    *,
    home: Path | None = None,
    project: Path | None = None,
) -> Path:
    if agent not in SUPPORTED_AGENTS:
        raise InstallError(f"Unsupported agent: {agent}")
    if scope not in {"user", "project"}:
        raise InstallError(f"Unsupported scope: {scope}")

    if scope == "user":
        root = (home or Path.home()).expanduser()
        relative = {
            "claude": Path(".claude/skills") / SKILL_NAME,
            "codex": Path(".agents/skills") / SKILL_NAME,
            "hermes": Path(".hermes/skills/media") / SKILL_NAME,
        }[agent]
    else:
        root = (project or Path.cwd()).expanduser()
        relative = {
            "claude": Path(".claude/skills") / SKILL_NAME,
            "codex": Path(".agents/skills") / SKILL_NAME,
            "hermes": Path(".hermes/skills/media") / SKILL_NAME,
        }[agent]
    return (root / relative).resolve(strict=False)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def install_skill(source: Path, destination: Path, *, force: bool = False, dry_run: bool = False) -> Path:
    source = source.expanduser().resolve(strict=True)
    destination = destination.expanduser().resolve(strict=False)
    if not (source / "SKILL.md").is_file():
        raise InstallError(f"Source is not an Agent Skill: {source}")
    if source == destination or source in destination.parents:
        raise InstallError("Destination must not be the source or one of its children")
    occupied = destination.exists() or destination.is_symlink()
    if occupied and not force:
        raise InstallError(f"Destination already exists (use --force to replace): {destination}")
    if dry_run:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{SKILL_NAME}.install-{uuid.uuid4().hex}"
    backup = destination.parent / f".{SKILL_NAME}.backup-{uuid.uuid4().hex}"
    try:
        shutil.copytree(source, temporary, symlinks=False)
        if occupied:
            destination.rename(backup)
        temporary.rename(destination)
        if backup.exists() or backup.is_symlink():
            _remove_path(backup)
    except Exception:
        _remove_path(temporary)
        if (backup.exists() or backup.is_symlink()) and not (destination.exists() or destination.is_symlink()):
            backup.rename(destination)
        raise
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install the KIE Media Agent Skill")
    parser.add_argument(
        "--agent", action="append", choices=[*SUPPORTED_AGENTS, "all"], required=True,
        help="Target host; repeat to install for multiple hosts",
    )
    parser.add_argument("--scope", choices=["user", "project"], default="user")
    parser.add_argument("--project", type=Path, help="Project root for --scope project (default: current directory)")
    parser.add_argument("--home", type=Path, help="Override user home for testing or managed environments")
    parser.add_argument("--source", type=Path, help="Override canonical skill source")
    parser.add_argument("--force", action="store_true", help="Atomically replace an existing installation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    source = (args.source or repo_root / "skills" / SKILL_NAME).expanduser()
    requested = list(args.agent)
    agents = list(SUPPORTED_AGENTS) if "all" in requested else list(dict.fromkeys(requested))
    installed = []
    try:
        for agent in agents:
            destination = resolve_destination(
                agent, args.scope,
                home=args.home,
                project=args.project,
            )
            result = install_skill(source, destination, force=args.force, dry_run=args.dry_run)
            installed.append({"agent": agent, "scope": args.scope, "path": str(result), "dry_run": args.dry_run})
    except (InstallError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"installed": installed}, indent=2))
    else:
        for item in installed:
            prefix = "Would install" if item["dry_run"] else "Installed"
            print(f"{prefix} {item['agent']}: {item['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

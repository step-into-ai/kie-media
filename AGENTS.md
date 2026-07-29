# KIE Media agent instructions

## Purpose

KIE Media is a Python 3.11+ CLI and open Agent Skill for safe KIE.ai image/video production. Use `skills/kie-media/SKILL.md` as the canonical production workflow. Repository-specific Claude and Codex adapters only point to that source.

## Bootstrap

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

A `KIE_API_KEY` is required only for uploads, credits, and generation. Offline planning, tests, schema checks, and evals must work without credentials.

## Agent entry points

```bash
kie-media agent plan "<brief>" --json
kie-media agent run "<brief>" --max-jobs 5 --json
PYTHONPATH=src:. python3 -m unittest discover -s tests -v
PYTHONPATH=src:. python3 scripts/evaluate_planner.py --json
PYTHONPATH=. python3 scripts/sync_codex_plugin.py --check
```

## Safety contract

- Run `agent plan` before non-trivial production and inspect `status`, `missing_inputs`, `capability_gaps`, `estimated_jobs`, and stages.
- Never retry paid task creation automatically.
- Never bypass `--max-jobs`; raise it only when the user requested and reviewed a larger plan.
- Reuse the same manifest when resuming. `needs_recovery` requires task/history inspection, not a fresh generation.
- Do not commit `.env`, generated media, manifests, task payloads, or credentials.
- Do not claim Higgsfield-only capabilities; follow the documented gap matrix.

## Repository layout

- `src/kie_media/` — CLI, KIE client, models, planner/executor
- `skills/kie-media/` — canonical cross-agent Agent Skill
- `.agents/skills/` — Codex repository discovery adapter
- `.claude/skills/` — Claude Code repository discovery adapter
- `agents/` — machine-readable role manifest
- `schemas/` — production-plan and run-manifest JSON Schemas
- `evals/` — offline planner scenarios
- `scripts/` — installer, eval, and release/security helpers
- `tests/` — standard-library unittest suite

## Change discipline

1. Add a failing regression test before behavior changes.
2. Keep planning credential-free and deterministic.
3. Validate all media/model inputs before upload or paid task creation.
4. Run the complete test suite, offline evals, compileall, wheel build, `git diff --check`, and secret scan before release.
5. Do not stage generated `build/`, `dist/`, `*.egg-info`, `outputs/`, or `kie-media-output/` artifacts.

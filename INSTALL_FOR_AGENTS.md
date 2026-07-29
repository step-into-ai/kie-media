# Install KIE Media for AI agents

KIE Media follows the open [Agent Skills specification](https://agentskills.io/specification). The canonical skill is `skills/kie-media/`; adapters and the installer make the same workflow discoverable without maintaining divergent copies.

## 1. Install the CLI

From a clone of this repository:

```bash
python3 -m venv .venv
.venv/bin/pip install .
```

For a user-level command, `pipx install .` or `uv tool install .` are also supported when those tools are available.

Verify without credentials or spend:

```bash
kie-media --help
kie-media agent plan "Create one editorial image of a lunar greenhouse" --json
```

## Codex plugin install from GitHub

After the repository is published, Codex 0.136+ can install the packaged plugin directly:

```bash
codex plugin marketplace add step-into-ai/kie-media
codex plugin add kie-media@kie-media
```

The repository also remains usable through `.agents/skills` and the cross-agent installer below.

## 2. Install the Agent Skill

Install for one or more hosts:

```bash
python3 scripts/install_agent_skill.py --agent claude
python3 scripts/install_agent_skill.py --agent codex
python3 scripts/install_agent_skill.py --agent hermes
python3 scripts/install_agent_skill.py --agent all
```

Use `--scope project --project /path/to/project` for a repository-local copy, `--dry-run` to inspect destinations, and `--force` to atomically replace an older installation.

| Host | User scope | Repository scope |
|---|---|---|
| Claude Code | `~/.claude/skills/kie-media` | `.claude/skills/kie-media` |
| OpenAI Codex | `~/.agents/skills/kie-media` | `.agents/skills/kie-media` |
| Hermes Agent | `~/.hermes/skills/media/kie-media` | `.hermes/skills/media/kie-media` |
| GitHub Copilot | root `AGENTS.md` + `.github/copilot-instructions.md` | included in this repository |

For another Agent Skills-compatible host, copy the complete `skills/kie-media/` directory to that host's skills directory. Do not copy only `SKILL.md`; its references are part of the workflow.

## 3. Configure execution

Only real generation needs a KIE key:

```bash
export KIE_API_KEY="..."
kie-media credits --json
```

Never commit the key. Agents should plan first, inspect `estimated_jobs`, and honor the default execution limit of five jobs. A larger bundle requires an explicit `--max-jobs N`.

## 4. Verify discovery without spending credits

Ask the host agent:

> Plan one 16:9 cinematic KIE video of a solar farm at sunrise. Do not generate it.

Expected behavior:

- it selects the `kie-media` skill,
- runs or recommends `kie-media agent plan`,
- reports workflow `video`, status `ready`, and one estimated job,
- does not ask for a key and does not create a KIE task.

Run the portable offline eval suite for stronger verification:

```bash
PYTHONPATH=src:. python3 scripts/evaluate_planner.py --json
```

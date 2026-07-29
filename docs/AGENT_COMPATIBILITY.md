# Agent compatibility

KIE Media separates a standards-compatible Agent Skill from host-specific discovery files.

## Canonical source

`skills/kie-media/SKILL.md` follows the open Agent Skills format: YAML frontmatter with `name` and `description`, Markdown instructions, and progressively disclosed files under `references/`.

## Supported hosts

### Claude Code

- Repository discovery: `.claude/skills/kie-media/SKILL.md`
- User installation: `~/.claude/skills/kie-media/SKILL.md`
- Project context: root `CLAUDE.md`

Claude Code documents both project and personal skill directories and follows the Agent Skills standard.

### OpenAI Codex

- Repository discovery: `.agents/skills/kie-media/SKILL.md`
- User installation: `~/.agents/skills/kie-media/SKILL.md`
- Installable plugin: `plugins/kie-media/.codex-plugin/plugin.json` + `.agents/plugins/marketplace.json`
- Repository context: root `AGENTS.md`

Current Codex documentation scans `.agents/skills` from the working directory to repository root. For reusable GitHub distribution, this repository also follows the official Codex plugin/marketplace format; older examples using only `~/.codex/plugins` are not the canonical source.

### Hermes Agent

The installer copies the canonical skill to `~/.hermes/skills/media/kie-media` by default. Managed/profile environments can pass `--home` or use project scope.

### GitHub Copilot

The repository includes `AGENTS.md` and `.github/copilot-instructions.md`, both supported repository instruction surfaces. Copilot is directed to the canonical skill rather than a forked workflow.

### Other hosts

Any Agent Skills-compatible host can consume the complete `skills/kie-media/` directory. The CLI is the stable integration boundary, so the host does not need Python API knowledge.

## Design rules

- One canonical skill; adapters contain discovery only.
- Planning requires no secret and no network.
- Paid execution is explicit, bounded by `--max-jobs`, checkpointed, and never automatically retried.
- Host adapters must not add model claims or relax safety rules.

## Upstream references

- Agent Skills specification: <https://agentskills.io/specification>
- Claude Code skills: <https://code.claude.com/docs/en/skills>
- Codex skills: <https://learn.chatgpt.com/docs/build-skills>
- GitHub Copilot repository instructions: <https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions>

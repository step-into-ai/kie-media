# GitHub Copilot instructions

Read and follow the root [`AGENTS.md`](../AGENTS.md) for repository development, testing, and paid-task safety.

For KIE image/video production behavior, use [`skills/kie-media/SKILL.md`](../skills/kie-media/SKILL.md) as the canonical Agent Skill. Planning must remain deterministic, credential-free, and safe to run in CI. Do not perform a live KIE generation as a test and never expose `KIE_API_KEY` or local manifests.

Before proposing a change, run the standard-library unit tests and offline planner evals documented in `AGENTS.md`.

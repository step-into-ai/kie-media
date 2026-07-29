# KIE Media agent suite

The suite is one coordinated production system, not five unrelated chat personas. Any Agent Skills-compatible host—Claude Code, Codex, Hermes, or another orchestrator—can load the `kie-media` skill. The deterministic planner emits model-aware stages; the host supplies judgment for research, visual review, and delivery.

## State machine

1. **Route** — Creative Director classifies the request.
2. **Clarify** — only if a required product/reference image is missing.
3. **Plan** — `kie-media agent plan ... --json` returns a reproducible plan with exact argv commands.
4. **Produce** — `kie-media agent run ... --json` runs paid generation stages sequentially and never retries task creation.
5. **Review** — the host agent uses vision on every candidate. Campaigns stop here before an animation can spend more credits.
6. **Continue** — selected stills can be animated with `video-kling-image` or `video-default`.
7. **Deliver** — return persistent local files plus a concise model/task summary.

## Why roles are explicit but not separate processes

Separate LLM subprocesses would add cost and coordination risk without improving deterministic routing or API execution. The role boundary is preserved in every `ProductionPlan.stage.role`; the host may delegate a genuinely independent research or review stage when useful.

## Safety boundaries

- Planning never needs a KIE key and never spends credits.
- `agent run` is the explicit paid operation and refuses plans above five jobs unless `--max-jobs` is raised deliberately.
- Static model and wait validation happens before upload/task creation.
- Paid task creation is never retried automatically.
- Multi-stage campaign runs stop at a blocking visual review gate.
- Manifests, history, and downloaded results are owner-only (`0600`).

---
name: kie-media
description: "Use when planning or producing KIE image/video workflows, product visuals, marketplace cards, campaigns, or image animation."
version: 1.0.0
author: Olymp
license: MIT
compatibility: Requires the kie-media CLI; planning needs Python 3.11+, execution needs network access and KIE_API_KEY.
metadata:
  hermes:
    tags: [kie, image-generation, video-generation, agents, product-photography, marketplace]
---

# KIE Media Production Agents

Use the `kie-media` CLI as the stable execution backend and this skill as the orchestration contract. The system adapts useful patterns from Higgsfield's public MIT-licensed skills to documented KIE APIs; it does not claim backend-only Higgsfield features.

## Runtime and entry points

```bash
kie-media agent plan "<natural brief>" --json
kie-media agent run "<natural brief>" --max-jobs 5 --json
```

If `kie-media` is missing, follow the repository's `INSTALL_FOR_AGENTS.md`. Do not reimplement the planner or call KIE endpoints directly.

Add repeated `--media <image-path>`, `--reference-video <path>`, `--reference-audio <path>`, `--count`, `--aspect-ratio`, `--duration`, `--budget fast|quality`, `--mode`, `--scope`, and `--output-dir` when supplied or obvious. Typed video/audio references are valid only for the `video` workflow.

## Operating flow

1. Run `agent plan` first for every non-trivial request.
2. Read `workflow`, `status`, `missing_inputs`, `capability_gaps`, `estimated_jobs`, and the ordered stages.
3. If `needs_input`, ask only for the listed blocker. Do not start a generic substitute.
4. If `hybrid`, explain the exact missing primitive and use another installed tool only when it can honestly supply it.
5. When the user asks to persist a plan, pass `--save <path>` to `agent plan` in the same CLI command. Never recreate the JSON with a generic file-writing tool; the planner writes it atomically with mode `0600`.
6. If `ready` and the user requested creation, run `agent run`; for multi-stage work retain its returned manifest path. Natural creation intent is authorization for the declared stages. Do not add a ceremonial confirmation loop.
7. Stay quiet during polling. Do not narrate task internals.
8. For `awaiting_review`, inspect every generated file with vision and apply the review rubric. If animation was requested, invoke the exact same brief/options with the same `--manifest` plus `--selected-file <winner>`; never start a fresh campaign run.
9. If state is `needs_recovery`, do not retry the stage. Inspect the manifest's `running_stage`, local history and KIE task status first because paid creation may have succeeded.
10. Deliver persistent local media files, not just temporary KIE URLs. Keep the reply concise and in the user's language.

## Agent roles

- **Creative Director** — routes intent and detects genuine blockers.
- **Prompt Engineer** — creates short model-aware prompts and shared visual constraints.
- **Image Producer** — runs validated image stages.
- **Video Producer** — runs motion-focused video stages.
- **Reviewer/Delivery** — performs visual QA, selects winners and returns files.

These are explicit stage roles in the plan, not wasteful standalone personas. Delegate only research or review work that is truly independent.

## Routing defaults

- general design/text image → `image-default`
- fast or reference-driven image → `image-fast`
- serious video → `video-default`
- fast video → `video-fast`
- animate one still → `video-kling-image`
- product visual → `product-photoshoot`
- listing/A+ image set → `marketplace-cards`
- multi-asset creative → `campaign` with a review gate
- narrated explainer → hybrid plan only until audio/assembly adapters exist

Never invent a model or backend feature. Inspect with `kie-media models --json` and `kie-media model <alias> --json`.

## Cost and safety

- Planning is free and needs no KIE key.
- `estimated_jobs` is a job count, not a credit estimate; the current adapter has no reliable preflight cost endpoint.
- `agent run` defaults to `--max-jobs 5`. Raise that cap only after the free plan was inspected and the larger scope was actually requested.
- Never retry paid task creation automatically.
- Reuse matching manifests: completed paid stages are skipped, a plan fingerprint prevents cross-plan resume, and canonical private plan/manifest locks prevent concurrent duplicates through UUID names or symlink aliases.
- Rejoin known tasks with `kie-media wait <task-id>`.
- Local media, history and manifests are private (`0600`).
- Do not upload or generate when the static plan is invalid.
- For large bundles such as marketplace `full-set`, ensure the user actually requested that scope; do not silently expand a single image request.

## Direct executor commands

```bash
kie-media credits --json
kie-media models --json
kie-media generate <alias> --prompt "..." --json
kie-media status <task-id> --json
kie-media wait <task-id> --json
kie-media history --json
```

## References

Load when needed:

- `references/workflows.md` — workflow semantics and execution rules
- `references/routing-and-models.md` — intent routing/model choices
- `references/prompting-and-review.md` — prompt and visual-QA rules
- `references/higgsfield-gap-matrix.md` — honest parity/limitations
- `references/cookbook.md` — executable recipes

# Agent architecture

## Components

- `kie_media.agent` — intent router, production planner, independent prompt templates, plan executor, private manifests.
- `kie_media.models` — authoritative local KIE contracts and aliases.
- `kie_media.client` — uploads, jobs, polling, download verification.
- `kie_media.history` — redacted audit trail.
- Agent Skills-compatible host — natural-language orchestration and visual review using `skills/kie-media`.

## ProductionPlan contract

A plan contains:

- `workflow`, `route_reason`, `status`, `executable`
- mode/scope/aspect/duration/count/budget
- required and missing inputs
- explicit backend capability gaps
- ordered stages with `role`, `action`, dependencies and argv-style command arrays
- `estimated_jobs` (job count, never a fabricated credit estimate)

Statuses:

- `ready` — executable generation stages exist
- `needs_input` — a real reference/product input is missing
- `hybrid` — the workflow needs a backend primitive outside KIE Media V1

## Execution

`agent run` accepts only planner-produced `kie-media` argv commands. It rejects plans above five declared jobs unless the caller deliberately raises `--max-jobs`. It runs without a shell, one stage at a time. Before every paid stage it atomically checkpoints a private `0600` manifest; successful results are checkpointed immediately afterward. Default manifests have unique names.

Pass the same `--manifest` to resume. Canonical path resolution plus private plan- and manifest-level locks cover the complete read → paid stage → checkpoint transaction: the same production plan cannot run concurrently even with different default manifest names or symlink aliases. Completed stages are skipped. A manifest whose `running_stage` has no recorded result returns `needs_recovery` instead of risking a duplicate paid job; inspect KIE history/status first. Plan fingerprints prevent a different brief from reusing an old manifest.

A blocking review stage returns `awaiting_review`. For campaigns that request animation, resume the same manifest with `--selected-file <generated-candidate>`; only a candidate already recorded in that manifest is accepted.

## Workflow routing

Priority is intentional:

1. marketplace listing/cards
2. narrated explainer
3. campaign/best-candidate chain
4. image-to-video
5. video (including product-video intent and reference images)
6. product photoshoot
7. generic image

This prevents a phrase such as “hero banner showing serum being applied” from routing to a generic image model and makes output-format tie-breakers deterministic.

## Review rubric

Inspect every candidate for:

1. prompt fidelity and requested format
2. reference/product identity
3. composition and usable negative space
4. typography and factual claims
5. anatomy/geometry/temporal stability
6. artifacts, logos and watermarks
7. consistency across a set

Do not regenerate automatically merely because an output is imperfect. Diagnose the failure, adjust one prompt/parameter dimension, and resubmit only the failed stage when the user requested a finished asset.

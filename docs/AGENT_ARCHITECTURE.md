# Agent architecture

## Components

- `kie_media.agent` — intent router, production planner, independent prompt templates, plan executor, private manifests.
- `kie_media.models` — curated offline KIE contracts, aliases, and shared validation.
- `kie_media.catalog` — official KIE `llms.txt` discovery, defensive OpenAPI extraction, natural-name resolution, and private last-known-good cache.
- `kie_media.preferences` — private per-user tier/model/job defaults.
- `kie_media.client` — uploads, jobs, polling, download verification.
- `kie_media.history` — redacted audit trail.
- `kie_media.storage` — atomic JSON and native Windows/POSIX process locks.
- `kie_media.language` — allowlisted KIE language transports, JSON/SSE responses, no automatic paid retry.
- `kie_media.inspection` — credential-free runtime diagnostics and explicit documentation coverage.
- `kie_media.projects` / `project_cli` — editable scenes, entity library, immutable job receipts, review, selective invalidation and handoff.
- `kie_media.media` — shell-free FFmpeg montage and ffprobe technical checks.
- Agent Skills-compatible host — natural-language orchestration and visual review using `skills/kie-media`.

## ProductionPlan contract

This section describes the legacy `agent` planner. Multi-scene films use `project` instead; the complete operating contract is in [projects.md](../skills/kie-media/references/projects.md).

Project jobs checkpoint `submitting` before paid creation and `submitted` as soon as the provider task ID is known. Known IDs resume polling/download. An unknown submission blocks further production until associated with its verified task ID. Scene fingerprints determine reuse; downloaded bytes are checked against hashes before review/reuse/render. A motion edit affects its video; a visual/reference edit affects its image and video; narration affects its audio. Final montage has a separate content-derived cache. Reviews are recorded host/user judgments, not an autonomous vision scorer. Active copies on different machines are not covered by a distributed lock.

POSIX files use owner-only modes. Windows uses inherited folder ACLs and native byte-range locks; chmod modes are not advertised as Windows ACL protection.

A plan contains:

- `workflow`, `route_reason`, `status`, `executable`
- mode/scope/aspect/duration/count, legacy budget, and `budget|balanced|premium` tier
- required and missing inputs
- explicit backend capability gaps
- ordered stages with `role`, `action`, dependencies and argv-style command arrays
- `estimated_jobs` plus optional `estimated_credits` based only on complete local observations

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

## Model resolution and personalization

Explicit user model → personal default → tier ranking → curated fallback. Explicit compatible model wishes always win. Natural names are resolved at runtime against KIE's official documentation; exact technical IDs remain available to expert users. Separate text/reference model pages are disambiguated from the workflow's media context.

Remote documentation is untrusted data. The catalog accepts only bounded HTTPS content from `docs.kie.ai`, parses YAML with aliases disabled, follows only local OpenAPI references, and persists only validated model IDs plus typed field contracts. Free prose never enters agent instructions. A failed or contradictory refresh cannot replace a previously validated schema.

`budget` uses fast/lower-resolution curated routes, `balanced` uses standard settings, and `premium` raises supported quality/resolution without increasing requested job count or bypassing `--max-jobs`. Since KIE has no general trustworthy preflight price endpoint, exact prices are never inferred from tier labels.

Successful `status`/`wait` results include `credits_consumed` and enter the existing private history. The planner computes per-model medians and exposes an estimate only when every paid stage is covered. These mutable informational fields are deliberately excluded from the resume fingerprint.

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

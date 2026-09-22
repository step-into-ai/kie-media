# Changelog

## [0.4.0] - 2026-09-22

- Native Windows locks, atomic state, UTF-8 CLI output and three-platform CI.
- Dynamic task/audio/promptless and nested/alternative input schemas; explicit catalog coverage audit.
- KIE Chat Completions, Responses, Claude Messages and Gemini transports with streaming and no automatic paid retry.
- Editable scene projects, targeted invalidation, entity library, per-stage receipts/reviews and known-task resume.
- KIE narration/music stages, local FFmpeg montage, scene captions, technical media checks and imported assets.
- Project dossiers, checksum-verified ZIP handoff and five demonstration recipes.
- No claim of complete live provider validation, guaranteed credit ceilings, automatic visual QA or native 3D.

All notable changes are documented here. The format follows Keep a Changelog and versions follow Semantic Versioning.

## [Unreleased]

## [0.3.0] - 2026-07-29

### Added

- Runtime discovery of current KIE models by natural name through the official `llms.txt` and per-model OpenAPI documentation.
- Private validated model cache with last-known-good offline recovery and context-aware text/reference variant selection.
- `budget`, `balanced`, and `premium` planning tiers plus explicit `--image-model` and `--video-model` precedence.
- Private per-user model, tier, exclusion, and job-cap preferences.
- Local observed-credit profiles from successful KIE task status, with clearly labelled median-based plan estimates.

### Changed

- Curated aliases are now verified offline fallbacks rather than the catalog ceiling.
- Premium and budget tiers select distinct supported quality/resolution settings without changing requested job counts.
- Production plans use schema version 2 and exclude mutable observed-credit estimates from resume fingerprints.

### Security

- Remote model documentation is restricted by host, scheme, redirect policy, and response size; YAML aliases are disabled.
- Only validated structured OpenAPI fields are retained. Invalid refreshes cannot replace cached schemas.
- Discovery and all release tests remain free of paid generation.

## [0.2.0] - 2026-07-29

### Added

- Deterministic natural-language planner and safe multi-stage executor.
- Product photoshoot, marketplace cards, campaigns, image-to-video, video, image, and hybrid explainer workflows.
- Visual campaign review gates, resumable private manifests, fingerprints, paid-stage checkpoints, and canonical plan/manifest locks.
- Open Agent Skill with repository discovery for Claude Code and Codex, plus Hermes and GitHub Copilot guidance.
- Cross-agent installer, JSON Schemas, offline planner evals, CI matrix, and tag-based GitHub releases.
- Explicit `--max-jobs` execution budget for larger paid bundles.

### Security

- No automatic retry of paid task creation.
- Static validation before upload/task creation.
- Owner-only persisted artifacts and duplicate-run protection.

## [0.1.0] - 2026-07-28

### Added

- Initial KIE.ai image/video CLI with curated aliases, uploads, polling, downloads, and history.

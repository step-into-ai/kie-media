# Changelog

All notable changes are documented here. The format follows Keep a Changelog and versions follow Semantic Versioning.

## [Unreleased]

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

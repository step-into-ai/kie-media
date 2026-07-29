# KIE Media

[![CI](https://github.com/step-into-ai/kie-media/actions/workflows/ci.yml/badge.svg)](https://github.com/step-into-ai/kie-media/actions/workflows/ci.yml)
[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-compatible-7c3aed)](https://agentskills.io/specification)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776ab)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Agent-friendly image and video production through the public KIE.ai API. KIE Media combines a robust CLI with a deterministic production planner, resumable multi-stage execution, visual review gates, and an open Agent Skill for Claude Code, OpenAI Codex, Hermes Agent, GitHub Copilot, and other compatible hosts.

The project adapts useful workflow ideas from Higgsfield's public MIT-licensed skills to documented KIE APIs. It does **not** claim Higgsfield backend parity.

[![Get KIE.ai API access](https://img.shields.io/badge/Get_KIE.ai_API_Access-111827?style=for-the-badge)](https://kie.ai?ref=cf44220beef51bafae441080f5080412)

> **Referral disclosure:** The KIE.ai account link above is an affiliate/referral link. Using it may support the project at no additional cost to you. KIE Media remains an independent open-source project and is not an official KIE.ai product.

## Highlights

- live KIE model discovery by natural name or exact model ID, with curated offline fallbacks
- validated OpenAPI parameter schemas cached locally with last-known-good recovery
- personal image/video defaults and `budget`, `balanced`, or `premium` campaign tiers
- natural-language routing into validated production plans
- product photoshoots, marketplace/A+ cards, campaigns, images, videos, and image-to-video
- free, offline planning without a KIE key
- explicit `--max-jobs` budget before paid multi-job execution
- visual campaign review gate before downstream animation
- resumable `0600` manifests with fingerprints and paid-stage checkpoints
- canonical plan/manifest locks against concurrent duplicate generation
- no automatic retry of non-idempotent paid task creation
- typed image, video, and audio reference handling
- portable Agent Skill, Codex plugin, JSON Schemas, and offline eval suite

## What you can build

| Workflow | What KIE Media does |
|---|---|
| Single images | Posters, editorial visuals, product heroes, typography-led designs, reference edits, and social assets |
| Single videos | Text-to-video and multimodal clips with duration, aspect ratio, resolution, image, video, and audio references |
| Image-to-video | Animates an existing still with motion-focused prompting and validated start-frame handling |
| Product photoshoots | Produces coordinated studio, lifestyle, hero, detail, scale, flat-lay, packaging, and moodboard variants |
| Marketplace sets | Plans main images, supporting product images, A+ content, or a complete listing bundle |
| Campaigns | Generates several still candidates, pauses for visual review, then animates only the selected winner |
| Model discovery | Finds newly documented KIE models by natural name, validates their OpenAPI inputs, and caches them without a plugin release |
| Personal routing | Remembers preferred image/video models, exclusions, default tier, and maximum paid jobs locally |
| Cost-aware planning | Offers `budget`, `balanced`, and `premium` profiles and learns observed credits from completed jobs without inventing prices |
| Safe automation | Plans for free, validates before upload, limits paid jobs, checkpoints execution, resumes completed stages, and blocks ambiguous retries |

The same repository works as a command-line tool and as an agent skill for Claude Code, OpenAI Codex, Hermes Agent, GitHub Copilot, and generic Agent Skills-compatible hosts.

## Install the CLI

```bash
git clone https://github.com/step-into-ai/kie-media.git
cd kie-media
python3 -m venv .venv
.venv/bin/pip install .
```

For a user-level command, install the clone with `pipx install .` or `uv tool install .` when either tool is available.

Planning works immediately and never spends credits:

```bash
kie-media agent plan "Create one editorial image of a lunar greenhouse" --json
```

Set `KIE_API_KEY` only for real uploads, credit checks, or generation:

```bash
export KIE_API_KEY="..."
kie-media credits --json
```

The CLI can also read the key from `~/.hermes/.env`, `$HERMES_HOME/.env`, the current `.env`, an explicit `--env-file`, or `$KIE_MEDIA_ENV_FILE`. Never commit any of these files.

## Install for agents

The canonical Agent Skill lives at [`skills/kie-media/`](skills/kie-media/) and follows the open Agent Skills specification.

### Codex plugin from GitHub

Codex 0.136+ can install the repository's packaged plugin and marketplace:

```bash
codex plugin marketplace add step-into-ai/kie-media
codex plugin add kie-media@kie-media
```

### Cross-agent installer

From a clone:

```bash
python3 scripts/install_agent_skill.py --agent claude
python3 scripts/install_agent_skill.py --agent codex
python3 scripts/install_agent_skill.py --agent hermes
python3 scripts/install_agent_skill.py --agent all
```

| Host | Discovery/integration |
|---|---|
| Claude Code | `.claude/skills/kie-media` and root `CLAUDE.md` |
| OpenAI Codex | `.agents/skills/kie-media`, root `AGENTS.md`, and installable plugin |
| Hermes Agent | `~/.hermes/skills/media/kie-media` via installer |
| GitHub Copilot | root `AGENTS.md` and `.github/copilot-instructions.md` |
| Other hosts | copy the complete `skills/kie-media/` directory |

See [`INSTALL_FOR_AGENTS.md`](INSTALL_FOR_AGENTS.md) and [`docs/AGENT_COMPATIBILITY.md`](docs/AGENT_COMPATIBILITY.md).

## Quick start

```bash
kie-media models
kie-media model video-default
kie-media models --live --search "Seedream 5 Pro" --kind image
kie-media model "Seedream 5 Pro" --json
kie-media upload ./frame.png

kie-media image "Editorial poster for an AI media studio, precise typography" \
  --aspect-ratio 16:9 --resolution 1K

kie-media video "Cinematic dolly-in through a warm modern AI studio" \
  --duration 5 --aspect-ratio 16:9

kie-media generate image-fast --prompt "Character sheet, expressive poses" --wait
kie-media generate video-kling-image --prompt "Subtle camera push-in" \
  --image ./frame.png --wait

kie-media status <task-id>
kie-media wait <task-id>
kie-media history
```

New KIE models do not require a KIE Media release. `models --live` reads KIE's official `llms.txt`; `model <name>` retrieves the selected official Markdown page, extracts only its OpenAPI `createTask` schema, validates the model ID and field contracts, and stores the last validated result in a private local cache. Remote prose is never executed or injected into an agent prompt. If refresh fails, the last-known-good cache and curated aliases remain usable.

Name a model directly instead of looking up its technical ID:

```bash
kie-media image "Premium launch visual" --model "Seedream 5 Pro" --json
kie-media video "Cinematic product reveal" --model "Seedance 2 Mini" --json
```

When KIE documents separate text-to-image and image-to-image variants, the resolver uses the supplied media context. A technical model ID remains available as an expert passthrough, but only documented/cached models receive dynamic local schema validation.

Completed media is downloaded by default to the local KIE Media asset store because provider URLs can expire. Use `--no-wait`, `--no-download`, `--output-dir`, or `--json` when needed.

## Agent workflows

Plan locally first:

```bash
kie-media agent plan "Pinterest pin for my candle, cottagecore" \
  --media ./candle.jpg --count 3 --tier balanced --json
```

Profiles affect model and generation settings while an explicit model always wins:

```bash
kie-media agent plan "Economical launch campaign" --tier budget --count 3 --json
kie-media agent plan "Top-quality launch campaign" --tier premium \
  --image-model "Seedream 5 Pro" --video-model "Seedance 2 Mini" --json
```

- `budget` uses lower-cost curated models and settings without changing the requested job count.
- `balanced` is the default price/quality/speed compromise.
- `premium` raises supported quality settings, while retaining job and review limits.

Exact prices are never invented. Completed KIE status responses include `credits_consumed`; KIE Media learns per-model median credits in the local private history and shows `estimated_credits` only when every paid stage has relevant observations.

Persist personal defaults without editing the plugin:

```bash
kie-media preferences set --tier balanced \
  --image-model "Seedream 5 Pro" --video-model "Seedance 2 Mini" --max-jobs 5
kie-media preferences show --json
```

Execute only after inspecting `status`, `missing_inputs`, `capability_gaps`, and `estimated_jobs`:

```bash
kie-media agent run "Animate this photo with a slow camera pull-back" \
  --media ./still.jpg --duration 5 --max-jobs 1 --json
```

`agent run` defaults to a maximum of five declared paid jobs. Larger bundles require an explicit cap matching the reviewed plan:

```bash
kie-media agent plan "Complete marketplace listing set and A+ cards" \
  --media ./product.jpg --scope full-set --json

kie-media agent run "Complete marketplace listing set and A+ cards" \
  --media ./product.jpg --scope full-set --max-jobs 13 --json
```

Supported routes:

- `image`
- `video`
- `image-to-video`
- `product-photoshoot`
- `marketplace-cards`
- `campaign`
- `video-explainer` as an honest non-executable hybrid plan

Campaigns stop at `awaiting_review` after still generation. Resume the **same** manifest with a reviewed candidate:

```bash
kie-media agent run "Create three campaign images and animate the best one" \
  --count 3 --manifest ./campaign-run.json --selected-file ./winner.jpg \
  --max-jobs 4 --json
```

Existing matching manifests skip completed stages. Ambiguous interrupted stages return `needs_recovery` instead of risking a duplicate paid task.

## Curated aliases

- `image-default` → GPT Image 2
- `image-fast` → Nano Banana 2 Lite
- `image-bold` → Grok Imagine Image
- `video-default` → Seedance 2
- `video-fast` → Seedance 2 Fast
- `video-kling-fast` → Kling 3 Turbo text-to-video
- `video-kling-image` → Kling 3 Turbo image-to-video
- `video-bold` → Grok Imagine Video

Curated aliases are the verified offline fallback, not the catalog ceiling. Use `kie-media model "<natural model name>" --json` for live resolution and validated parameters. A current exact KIE model ID can still be used with `kie-media generate <model-id> --param key=value`; an undocumented passthrough receives only generic prompt validation.

## Offline verification

```bash
python3 -m compileall -q src tests scripts
PYTHONPATH=src:. python3 -m unittest discover -s tests -v
PYTHONPATH=src:. python3 scripts/evaluate_planner.py
python3 scripts/validate_distribution.py
python3 scripts/sync_codex_plugin.py --check
python3 scripts/security_scan.py
```

The repository includes:

- [`schemas/production-plan.schema.json`](schemas/production-plan.schema.json)
- [`schemas/run-manifest.schema.json`](schemas/run-manifest.schema.json)
- [`evals/scenarios.json`](evals/scenarios.json)
- Python 3.11/3.12/3.13 GitHub Actions CI
- tag-based wheel build, checksums, provenance attestation, and GitHub Release

## Security

- credentials are read locally and never stored in history or manifests
- remote documentation is restricted to HTTPS `docs.kie.ai`, size-bounded, parsed with YAML aliases disabled, and reduced to validated structured fields
- invalid refreshes never replace a last-known-good model schema
- static validation happens before media upload or paid task creation
- paid task creation is never retried automatically after ambiguous failure
- plans are fingerprinted and bounded by `--max-jobs`
- private state and downloaded media use owner-only permissions on POSIX systems
- generated outputs, local manifests, build artifacts, and `.env` files are ignored

See [`SECURITY.md`](SECURITY.md) for vulnerability reporting and the full security model.

## Documentation

- [Agent architecture](docs/AGENT_ARCHITECTURE.md)
- [Agent compatibility](docs/AGENT_COMPATIBILITY.md)
- [Cookbook](docs/COOKBOOK.md)
- [Higgsfield gap matrix](docs/HIGGSFIELD_GAP_MATRIX.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## API notes

Generation, task status, and credits use `https://api.kie.ai`. File uploads use KIE's documented separate host `https://kieai.redpandaai.co`; the similarly named path on `api.kie.ai` currently returns HTTP 404.

## License

MIT. See [`LICENSE`](LICENSE) and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

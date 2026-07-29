# KIE Media

Agent-friendly image and video generation through the public KIE.ai API. The CLI follows the useful interaction patterns of Higgsfield's public MIT-licensed skills while using only documented KIE endpoints and our own implementation.

## Features

- curated image/video model catalog with stable aliases
- `image` and `video` quality-first shortcuts
- generic pass-through for newly released KIE models
- asynchronous create/status/wait workflow
- local media auto-upload
- automatic result download (KIE URLs expire)
- local JSONL history without credentials
- JSON output for agents and scripts
- retry-safe polling and bounded waits; billable task creation is never retried automatically
- media signature/size validation and atomic `0600` downloads

## Install

```bash
cd /mnt/benny-data/home/benny/kie-media
python3 -m venv .venv
.venv/bin/pip install -e .
```

Set `KIE_API_KEY` in the environment, `~/.hermes/.env`, or pass `--env-file`.

## Quick start

```bash
kie-media credits
kie-media models
kie-media model video-default
kie-media upload ./frame.png

kie-media image "Editorial poster for an AI media studio, precise typography"   --aspect-ratio 16:9 --resolution 1K

kie-media video "Cinematic dolly-in through a warm modern AI studio"   --duration 5 --aspect-ratio 16:9

kie-media generate image-fast --prompt "Character sheet, expressive poses" --wait
kie-media generate video-kling-image --prompt "Subtle camera push-in" --image ./frame.png --wait

kie-media status <task-id>
kie-media wait <task-id>
kie-media history
```

`--wait` is the default. Completed media is downloaded to `~/.local/share/kie-media/assets/` (inside the active Hermes profile when `$HOME` is profile-scoped). Use `--no-wait`, `--no-download`, `--output-dir`, or `--json` when needed.

## Curated aliases

- `image-default` → GPT Image 2
- `image-fast` → Nano Banana 2 Lite
- `image-bold` → Grok Imagine Image
- `video-default` → Seedance 2
- `video-fast` → Seedance 2 Fast
- `video-kling-fast` → Kling 3 Turbo text-to-video
- `video-kling-image` → Kling 3 Turbo image-to-video
- `video-bold` → Grok Imagine Video

Use arbitrary current KIE model IDs with `kie-media generate <model-id> --param key=value`; unknown models are passed through with only the prompt requirement validated locally.

## Security

- the API key is read locally and never written to history
- generated URLs and metadata are stored, credentials/authorization headers are scrubbed
- history and downloaded media are forced to owner-only mode `0600`
- uploads/downloads reject empty, non-media, oversized, or signature-mismatched files
- non-idempotent paid task creation is not automatically retried after ambiguous failures
- no Higgsfield private APIs, scraping, or reverse engineering are used

## API notes

Generation, task status and credits use `https://api.kie.ai`. File uploads use KIE's documented separate host `https://kieai.redpandaai.co`; the similarly named path on `api.kie.ai` currently returns HTTP 404.

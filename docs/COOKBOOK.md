# KIE Media agent cookbook

## 1. Natural image request

```bash
kie-media agent plan "Quick photorealistic fox in a snowy forest" --tier budget --json
kie-media agent run "Quick photorealistic fox in a snowy forest" --tier budget --json
```

Routes to `image-fast` and delivers one downloaded image.

## Live wish-model discovery

```bash
kie-media models --live --search "Seedream 5 Pro" --kind image --json
kie-media model "Seedream 5 Pro" --json
kie-media agent plan "Premium launch visual" --workflow image --tier premium \
  --image-model "Seedream 5 Pro" --json
```

The explicit model wins over tier routing. Resolution is context-aware: no media selects the documented text-to-image variant; supplying `--media` selects a compatible reference/image-to-image variant. Discovery and planning do not spend KIE credits.

## Personal defaults

```bash
kie-media preferences set --tier balanced \
  --image-model "Seedream 5 Pro" --video-model "Seedance 2 Mini" --max-jobs 5
kie-media preferences show --json
```

Use `--no-preferences` for a one-off plan. Observed `credits_consumed` from successful `status` and `wait` responses appear as median-based estimates only when all planned paid stages are covered.

## 2. Animate an existing still

```bash
kie-media agent plan "Animate this photo; camera slowly pulls back" \
  --media ./still.jpg --duration 5 --json
kie-media agent run "Animate this photo; camera slowly pulls back" \
  --media ./still.jpg --duration 5 --json
```

Routes to `video-kling-image`; the prompt describes motion rather than redescribing the frame.

## 3. Product photoshoot

```bash
kie-media agent plan "Pinterest pin for my candle, cottagecore mood" \
  --media ./candle.jpg --count 3 --json
kie-media agent run "Pinterest pin for my candle, cottagecore mood" \
  --media ./candle.jpg --count 3 --json
```

Routes to `product-photoshoot / moodboard_pin / 2:3`. Each variant gets a coordinated but different camera treatment.

## 4. Marketplace full set

```bash
kie-media agent plan "Complete marketplace and A+ set for this serum" \
  --media ./serum.jpg --scope full-set --json
```

The plan exposes 13 paid image jobs before execution. The default execution budget blocks it; run with `--max-jobs 13` only when that exact scope was requested:

```bash
kie-media agent run "Complete marketplace and A+ set for this serum" \
  --media ./serum.jpg --scope full-set --max-jobs 13 --json
```

## 5. Campaign with review gate

```bash
kie-media agent run "Create three campaign images and animate the best one" \
  --count 3 --tier premium --aspect-ratio 4:5 \
  --manifest ./campaign-run.json --max-jobs 4 --json
```

The plan declares four paid jobs: three stills plus one selected animation. The first run generates the stills and returns `awaiting_review`. The host agent visually scores them, then resumes the same fingerprinted manifest with the winner:

```bash
kie-media agent run "Create three campaign images and animate the best one" \
  --count 3 --tier premium --aspect-ratio 4:5 --manifest ./campaign-run.json \
  --selected-file ./selected-generated-candidate.jpg --max-jobs 4 --json
```

If a run reports `needs_recovery`, do not invoke a fresh run. Inspect the recorded `running_stage`, local history and KIE task status to recover the possibly-created task without duplicate spend.

## 6. Narrated explainer

```bash
kie-media agent plan "Turn report.pdf into a one-minute narrated explainer" --json
```

Returns `status=hybrid` with explicit audio/voice/assembly gaps. It does not spend credits or pretend KIE Media V1 can assemble the final narrated timeline.

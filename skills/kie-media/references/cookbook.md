# Cookbook

```bash
# Free balanced planning
kie-media agent plan "Quick fox image in snow" --tier balanced --json

# Search and inspect a newly released KIE model without updating the plugin
kie-media models --live --search "Seedream 5 Pro" --kind image --json
kie-media model "Seedream 5 Pro" --json

# Use an explicitly requested model; it overrides tier routing
kie-media agent plan "Premium hero visual" --workflow image --tier premium \
  --image-model "Seedream 5 Pro" --json

# Persist personal defaults
kie-media preferences set --tier balanced \
  --image-model "Seedream 5 Pro" --video-model "Seedance 2 Mini" --max-jobs 5
kie-media preferences show --json

# One image
kie-media agent run "Editorial AI studio poster with precise typography" \
  --aspect-ratio 16:9 --tier premium --json

# Animate a still with an explicit video model
kie-media agent run "Slow camera pull-back with ambient motion" \
  --workflow image-to-video --media ./still.jpg --video-model "Kling 3 Turbo" \
  --duration 5 --max-jobs 1 --json

# Product pin
kie-media agent run "Pinterest pin for my candle, cottagecore" \
  --media ./candle.jpg --count 3 --tier balanced --json

# Marketplace plan before a large paid bundle
kie-media agent plan "Complete marketplace and A+ set" --media ./serum.jpg --scope full-set --json
kie-media agent run "Complete marketplace and A+ set" --media ./serum.jpg --scope full-set --max-jobs 13 --json

# Campaign; returns awaiting_review after still generation
kie-media agent run "Three campaign visuals and animate the best" \
  --count 3 --tier premium --image-model "Seedream 5 Pro" \
  --video-model "Seedance 2 Mini" --aspect-ratio 4:5 \
  --manifest ./campaign-run.json --max-jobs 4 --json
```

After `awaiting_review`, inspect files with vision and resume the fingerprinted plan with one recorded candidate. Repeat the same tier and explicit-model flags so the plan fingerprint remains stable:

```bash
kie-media agent run "Three campaign visuals and animate the best" \
  --count 3 --tier premium --image-model "Seedream 5 Pro" \
  --video-model "Seedance 2 Mini" --aspect-ratio 4:5 \
  --manifest ./campaign-run.json --selected-file ./winner.jpg --max-jobs 4 --json
```

If state is `needs_recovery`, inspect the manifest/history/task status. Do not launch a fresh run. A successful `status` or `wait` also records `credits_consumed` locally, allowing future plans to show observation-based estimates.

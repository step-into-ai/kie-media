# Cookbook

```bash
# Free planning
kie-media agent plan "Quick fox image in snow" --budget fast --json

# One image
kie-media agent run "Editorial AI studio poster with precise typography" --aspect-ratio 16:9 --json

# Animate a still
kie-media agent run "Slow camera pull-back with ambient motion" --workflow image-to-video --media ./still.jpg --duration 5 --json

# Product pin
kie-media agent run "Pinterest pin for my candle, cottagecore" --media ./candle.jpg --count 3 --json

# Marketplace plan before a large paid bundle
kie-media agent plan "Complete marketplace and A+ set" --media ./serum.jpg --scope full-set --json
kie-media agent run "Complete marketplace and A+ set" --media ./serum.jpg --scope full-set --max-jobs 13 --json

# Campaign; returns awaiting_review after still generation
kie-media agent run "Three campaign visuals and animate the best" --count 3 --aspect-ratio 4:5 --manifest ./campaign-run.json --max-jobs 4 --json
```

After `awaiting_review`, inspect files with vision and resume the fingerprinted plan with one recorded candidate:

```bash
kie-media agent run "Three campaign visuals and animate the best" --count 3 --aspect-ratio 4:5 --manifest ./campaign-run.json --selected-file ./winner.jpg --max-jobs 4 --json
```

If state is `needs_recovery`, inspect the manifest/history/task status. Do not launch a fresh run.

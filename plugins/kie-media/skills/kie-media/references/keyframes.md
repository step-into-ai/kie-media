# Pinned frames and reference-driven recreation

Use Grok Imagine 1.5's KIE contract for first, last, intermediate and loop frames.
Do not copy parameter names from xAI's direct API. `--keyframe` uses
`TIMESTAMP_S=URL_OR_FILE` and can be repeated up to four times. The CLI validates
the entire request before uploading any frame.

```bash
kie-media video "A gradual product reveal; the camera stays locked" --model video-grok-1-5 --duration 8 --start-image ./opening.png --keyframe 3=./middle.png --end-image ./closing.png --json
kie-media generate video-grok-1-5 --loop-image ./loop.png --param duration=8 --json
```

The current KIE OpenAPI schema accepts whole-second middle timestamps. They
must be inside the duration and at least 1/3 second apart (the release-text rule).
Use the same image at both ends for a loop. A loop image cannot conflict with
different explicit start/end frames. Use `kie-media model video-grok-1-5 --json`
for the implemented field types, ratios and limits. Frames can drive a promptless
request; text-only generation needs a nonempty prompt. Generated sound is model
output and must be checked with the visuals.

Kling 4 reference recreation is useful for richer source-video guidance with
named characters, product references and voices:

```bash
kie-media video "Follow the camera movement in @video_1; use the product in @image_1" --model video-kling-reference --reference-video ./movement.mp4 --reference-image ./product.png --duration 10 --param keep_original_sound=true --json
```

For named `elements` and `voices`, pass the documented nested JSON with
`generate --param`. Do not combine media parameters with dedicated media flags.
Local media in supported nested fields are uploaded only after schema validation.
Kling permits up to 10 images, 5 reference videos, 7 elements and 3 voices, with
15 total materials and 5 total videos including video elements. Declare every
`@name` used in the prompt. `@image_1` and `@video_1` use one-based indexes.

These models are curated offline additions. Other new models remain discoverable
through `models --live` and `model`; check the official schema before use.

Sources: [KIE Grok 1.5](https://docs.kie.ai/market/grok-imagine/1-5-preview),
[KIE changelog](https://kie.ai/changelog),
[Kling 4 references](https://docs.kie.ai/market/kling/v4-reference-to-video).

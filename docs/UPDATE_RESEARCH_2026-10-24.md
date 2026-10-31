# Video-control research, 24 October 2026

This is a documentation snapshot, not a certification of paid output quality.

## Higgsfield

The spoken product names were interpreted as **Genjutsu** and **Genjutsu Light**.
The official API lists Genjutsu Light with Motion Transfer
and Object Swap modes, both released 20 October 2026. Light uses the first 15
seconds of the source and preserves source audio. Its overview prose describes
that behavior, while the nearby table lists a 4-second duration; the current
public pages are inconsistent, so KIE Media does not encode a Light duration.
The full Genjutsu product keeps source motion while changing cast, location or
style and offers 1–30 second Motion Transfer and Object Swap modes.

- [Genjutsu Motion Transfer](https://open.higgsfield.ai/models/higgsfield/genjutsu/motion-transfer/v1.0/playground)
- [Genjutsu Light Motion Transfer](https://open.higgsfield.ai/models/higgsfield/genjutsu-light/motion-transfer/v1.0/playground)
- [Genjutsu Light Object Swap](https://open.higgsfield.ai/models/higgsfield/genjutsu-light/object-swap/v1.0/playground)

## KIE opportunities

| Need | Documented KIE model | Required inputs | Honest boundary |
|---|---|---|---|
| Character motion transfer | `kling-3.0/motion-control` | prompt (<=2500), one `input_urls` image, one `video_urls` clip, `mode`, `character_orientation` | Closest Genjutsu Light analogue. 3–30s source video, JPEG/PNG/JPG <=10MB image, MP4/QuickTime <=100MB video, both >340px and 2:5–5:2. |
| Source-video object replacement | `wan/2-7-videoedit` | prompt, `video_url`, `reference_image`, resolution, duration, audio setting | Source 2–10s, <=100MB, 240–4096px, 1:8–8:1; reference can be JPG, non-alpha PNG or WEBP, 240–8000px. 720p/1080p. `audio_setting=origin` preserves original audio; no mask/tracking. |
| Prompt-led restyle | `kling-3.0-omni/transformation` | prompt (<=3072), `video_urls`, resolution, ratio, audio | Source 3–15.5s, <=200MB, 700–4553px, <=8,294,400 pixels, 0.4–2 ratio and 24–60fps. The provider supports a reference branch; the initial recast adapter does not use it. |
| Multi-reference recreation | `kling-4.0/reference-to-video` | prompt with `@` tags, image/video references, optional elements/voices | Supports up to 10 images, 5 2–30s videos and 15 total materials. Source motion is guidance, not a guaranteed transfer. |
| First/middle/last frame control | `kling-4.0/keyframe-to-video` | prompt, `first_frame_url`, `keyframe_urls`, `last_frame_url`, duration, resolution | Correct KIE keyframe route; it is not a source-motion workflow. |

- [Kling 3 Motion Control](https://docs.kie.ai/market/kling/motion-control-v3)
- [Wan 2.7 Video Edit](https://docs.kie.ai/market/wan/2-7-videoedit)
- [Kling 3 Omni Transformation](https://docs.kie.ai/market/kling/v3-omni-transformation)
- [Kling 4 Reference to Video](https://docs.kie.ai/market/kling/v4-reference-to-video)
- [Kling 4 Keyframe to Video](https://docs.kie.ai/market/kling/v4-keyframe-to-video)

## Grok Imagine 1.5

KIE's validated live Grok schema now exposes `first_frame_url`, `last_frame_url`,
`loop_url`, and up to four `keyframes` objects shaped as
`{ "url", "timestamp_s" }`. Those field names are KIE-specific; use the
catalog-validated model contract rather than copying xAI names. Kling 4 remains
an additional explicit first/middle/last-frame route.

- [xAI video overview](https://docs.x.ai/developers/model-capabilities/video/overview)
- [KIE Grok Imagine 1.5 Preview](https://docs.kie.ai/market/grok-imagine/1-5-preview)

The current OpenAPI schema uses integer `timestamp_s`, even though the release
text describes minimum 1/3-second spacing. The CLI follows the schema and checks
spacing and the open interval `(0, duration)` before any upload. The release
notes can render field names without underscores; the live OpenAPI names above
are the contract used by this implementation.

## What shipped and what remains

Version 0.6 ships the three bounded recast adapters, Grok pinned frames/loops,
Kling 4 reference recreation, source/output review, recovery and current skill
instructions. It does not call Higgsfield's paid backend or infer its private
model/prompt pipeline. It keeps existing scene projects and creative directions.

The official [KIE changelog](https://kie.ai/changelog) also lists PixVerse V6 Max
and OmniHuman 2.0. They are useful candidates for storyboard-driven clips and
audio-driven characters, respectively. The existing live catalog can discover
their contracts without a plugin release. This update does not certify their
output quality or automatically change a user's saved default models.

The next useful quality check is a controlled comparison on the same authorized
source clip/reference: Genjutsu versus each relevant KIE engine, recording actual
credits, identity consistency, unwanted changes, camera/timing and sound. No paid
benchmark was run for this code update; those quality/cost results remain open.

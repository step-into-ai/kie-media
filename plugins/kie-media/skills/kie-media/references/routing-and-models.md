# Routing and models

Routing priority:

1. marketplace/listing/A+ → marketplace cards
2. narrated explainer → hybrid explainer plan
3. campaign / animate-best → campaign
4. animate existing image → image-to-video
5. video/clip/motion (including product video) → video
6. static product/brand visual → product photoshoot
7. otherwise → image

Curated aliases:

- `image-default`: GPT Image 2; typography, posters, layout-sensitive design
- `image-fast`: Nano Banana 2 Lite; references, edits, speed
- `image-bold`: Grok Imagine Image; expressive style
- `video-default`: Seedance 2; serious/multimodal/cinematic
- `video-fast`: Seedance 2 Fast
- `video-kling-fast`: Kling 3 Turbo text-to-video
- `video-kling-image`: Kling 3 Turbo image-to-video
- `video-bold`: Grok Imagine Video

Rules:

- Use `kie-media model <alias> --json` before passing uncertain parameters.
- Do not use uncatalogued model names just because the user suggests one; verify against the live documented KIE catalog before adding it.
- Reference-driven products/images choose `image-fast` because the current GPT Image alias is text-only.
- `estimated_jobs` reports volume, not price.

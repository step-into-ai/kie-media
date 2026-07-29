# Higgsfield → KIE agent gap matrix

Baseline inspected 2026-07-29:

- `higgsfield-ai/skills` commit `91051d3f260ae0792708c5eb0a87b07122ad3830`
- `higgsfield-ai/cli` commit `8827135df7601667f66cd36ce84cf72106d690c4`
- Public source: MIT-licensed skills, seven `SKILL.md` files, 72 Markdown artifacts, 13 eval scenarios.

This is an independent KIE implementation. Public workflow ideas are adapted; proprietary Higgsfield backend prompts/APIs are not copied or inferred.

| Public Higgsfield capability | KIE Media status | Implementation / decision |
|---|---|---|
| Generic image/video generation | **Complete** | Curated KIE model aliases, strict schemas, typed image/video/audio reference media, create/wait/download/history. |
| Agent installation/bootstrap | **Complete** | Managed Hermes `kie-media` skill plus CLI entrypoints. |
| Natural intent routing | **Complete** | `kie-media agent plan`, deterministic routing reason and blockers. |
| Prompt engineering guide | **Complete** | Model-aware short prompts, motion-only image-to-video prompts, positive constraints. |
| Product photoshoot modes | **Adapted** | Ten independent KIE templates and the same intent/tie-break taxonomy; no claim of Higgsfield's private enhancer. |
| Marketplace main/secondary/A+ cards | **Adapted** | `main`, `product-images`, `aplus`, `full-set`; 13 assets for full-set with claim-safety constraints. |
| Multi-step campaign | **Adapted** | Candidate generation → blocking vision review → fingerprinted manifest resume with a recorded selected candidate. |
| Media auto-upload and role validation | **Complete** | Local/remote type checks and KIE upload service. |
| Async jobs / rejoin | **Complete** | Status/wait/download plus per-stage atomic checkpoints, completed-stage skipping and ambiguous-stage `needs_recovery`. |
| Agent evals | **Adapted** | Routing, tie-break, missing-input, safety, execution and manifest tests. |
| Soul identity training | **Not available** | Current KIE adapter has reference-image consistency, not reusable identity-model training. Never fabricate a Soul equivalent. |
| Marketing Studio product/avatar registry | **Not available** | Product images are passed directly; no product URL importer, avatar catalog, hooks or settings registry. |
| Virality Predictor | **Not available** | No corresponding KIE analysis model is wired. Use a separate video-analysis workflow if requested. |
| Narrated explainer audio + assembler | **Hybrid gap** | Planner emits research/script/audio/video/assembly phases but blocks execution until audio and timeline adapters exist. |
| `draw_to_video` / `reframe` workflows | **Not wired** | No documented adapter in the current KIE catalog. |
| 3D generation | **Out of V1 scope** | KIE Media V1 is image/video. |
| Website builder/deployer | **Intentionally excluded** | Software/web production belongs to existing development/design skills. |
| Browser game generation/deployment | **Intentionally excluded** | Separate product domain, not a media-backend agent. |

## Parity definition

Parity means equivalent safe user outcomes where KIE exposes the required primitive. It does **not** mean copying Higgsfield names or pretending KIE has backend-only features. Every unavailable primitive is surfaced in `capability_gaps` and makes the plan non-executable.

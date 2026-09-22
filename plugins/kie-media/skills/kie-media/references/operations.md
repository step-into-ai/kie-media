# Models and operations

The official KIE documentation index contains model pages, transforms, retrieval operations, callbacks and guides. A page count is not a model count. Use `models --live --kind image|video|audio|chat|3d` for discovery and `model NAME --json` to inspect the selected schema. `catalog audit --refresh --json` inspects every indexed document and records coverage, reasons for unsupported/unavailable entries and a schema hash. It performs no generation. `--limit` bounds the inspected documents.

Keep support evidence distinct:

- discovered: a link exists in the index;
- schema validated: the request contract parsed successfully;
- adapter available: the endpoint family has a transport;
- live tested: an actual provider result was verified (the catalog audit never sets this true).

Image/video/audio operations using the common task endpoint share `generate`, `status`, `wait` and `download`. Prompts are optional at CLI level and required only where the selected schema requires them. Full nested objects, arrays and alternatives are validated. Use JSON `--param` values for complex inputs.

```bash
kie-media model "elevenlabs/text-to-speech-multilingual-v2" --json
kie-media generate "elevenlabs/text-to-speech-multilingual-v2" --param 'text="Your approved narration"' --json
kie-media model "Generate Music" --kind audio --json
kie-media generate ai-music-api/generate --param custom_mode=true --param instrumental=true --param model=V6 --param 'style="Warm ambient piano"' --param 'title="Project soundtrack"' --param duration=20 --json
kie-media model "Grok Imagine Image 2.0 Segment Map" --json
kie-media generate grok-imagine-image-2-0/segment-map --param task_id=VERIFIED_SOURCE_TASK_ID --json
```

These are billable operation examples, not preflight commands. Inspect each live contract first. Some provider constraints appear only in prose; do not assume successful schema validation proves every provider-side semantic rule. Task lineage matters for operations such as extension or segmentation. Retain the original task and returned operation data. Non-media operation results are exposed as `output`.

Language models have separate documented transports: Chat Completions, Responses, Claude Messages and native Gemini. Authentication stays with KIE's documented Bearer token on `api.kie.ai`; do not substitute native provider credentials. Requests are not retried automatically.

```bash
kie-media model "GPT 5.4" --kind chat --json
kie-media chat "GPT 5.4" "Draft three scene ideas for this approved brief" --json
kie-media chat "Gemini 2.5 Pro" --input-file ./request.json --stream
```

The JSON request file supports documented multimodal inputs, structured-output settings and tool declarations. Responses are data; the CLI does not execute returned tool calls. `--stream` emits JSONL events and a final result; interrupted streams must not be reported as complete. Never silently send the same paid request again after an ambiguous failure.

Remote docs remain allowlisted, size-bounded and YAML-alias-free. Transient HTML responses are rejected and retried at most twice at the same URL; HTML is never treated as an OpenAPI contract. Bad refreshes preserve the last known good cached model. Some pages remain unsupported when the provider does not expose a usable contract; report that accurately.

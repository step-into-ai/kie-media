# Recast an existing clip

Use `kie-media recast` when the input is a source video and the user wants to
transfer its performance, replace a visible subject/product, or change its look.
This is an independent KIE implementation of those outcomes. Higgsfield's
Genjutsu and Genjutsu Light are separate products with separate models.

| Mode | KIE engine | Reference |
|---|---|---|
| `motion-transfer` | `kling-3.0/motion-control` | Exactly one clear subject image, source video 3–30 seconds |
| `object-swap` | `wan/2-7-videoedit` | Exactly one subject/product image, source video 2–10 seconds |
| `restyle` | `kling-3.0-omni/transformation` | Source video 3–15.5 seconds, text direction |

`recast capabilities --json` returns the current implemented contract, including
format, dimensions, frame rate, resolution, reference count and audio limits.
Use the dedicated model commands for other engines; recast does not silently
substitute models. Restyle's initial CLI surface uses the video-only branch;
the provider's separate image/element branch can be used through `generate`.

## Plan and execute

```bash
kie-media recast capabilities --json
kie-media recast plan "Use this character for the source performance; retain camera movement and timing" --video ./performance.mp4 --reference-image ./character.png --mode motion-transfer --save ./work/motion-plan.json --json
kie-media recast run ./work/motion-plan.json --max-jobs 1 --json
```

Planning requires local files and FFprobe, but no key, network, uploads or paid
jobs. It checks media signatures, provider constraints and input hashes. Ask
for real missing media instead of inventing source files. User intent to make
the requested transformation authorizes its declared one-job run after the
plan is inspected; do not insert an additional confirmation loop.

For object replacement, name the exact subject and what should remain:

```bash
kie-media recast plan "Replace only the jacket with the reference. Preserve the wearer, camera, background and timing." --video ./source.mp4 --reference-image ./jacket.png --mode object-swap --keep-original-sound --save ./work/swap-plan.json --json
```

Wan's `audio_setting=origin` preserves original audio when
`--keep-original-sound` is requested. Other recast adapters reject that flag
before uploading. The default permits the documented engine audio behavior;
it does not guarantee silence or retention. Source duration determines output
duration. Trim inputs separately when needed; the workflow never silently
trims a user's clip. A larger `--max-jobs` does not increase the one-job plan.

## Resume, compare and review

Rerun the **same saved plan and manifest** after a polling/download interruption.
The known task is polled again; its paid creation is never repeated. If creation
was ambiguous and no task ID was received, inspect provider task history first:

```bash
kie-media recast recover ./work/recast-<fingerprint>-run.json --task-id <known-task-id> --json
kie-media recast run ./work/motion-plan.json --max-jobs 1 --json
kie-media recast compare ./work/recast-<fingerprint>-run.json --json
kie-media recast review ./work/recast-<fingerprint>-run.json accepted --note "Checked identity, hands, movement, timing, background and sound" --json
```

`compare` writes a local HTML viewer for source and output. Inspect both with
vision/video tools before recording acceptance; technical checks are not visual
review. Reject identity drift, broken anatomy, unintended changes, timing drift
or sound problems. Review is tied to artifact hashes. Changed files block resume
or review. `report` shows model, request receipt, task ID, actual credits when
available, output hashes and review state.

An intentional new variation uses a new saved plan with `--take 2` (and so on).
Do not rename a manifest to escape unresolved or rejected work. The ownership
record blocks another manifest for the same take in the output directory;
keep all takes for one production together. Do not delete ownership records.

## Evidence and limits

The adapters are grounded in official KIE schemas and tested offline. A
documented API contract does not establish the resulting identity consistency,
pixel preservation, motion fidelity or parity with Genjutsu. Wan's edit API
does not expose a mask or tracking controls in this workflow. Inspect actual
outputs; never describe the result as a tested Genjutsu clone without evidence.

Sources: [Kling motion control](https://docs.kie.ai/market/kling/motion-control-v3),
[Wan video edit](https://docs.kie.ai/market/wan/2-7-videoedit),
[Kling Omni transformation](https://docs.kie.ai/market/kling/v3-omni-transformation).

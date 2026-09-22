# Editable scene production

Use `project` for a multi-scene film, narrated explainer, an existing-media montage, or a request to change one scene. The older `agent plan video-explainer` remains a non-executable legacy outline; do not use it as the production executor.

## Make the brief executable

```bash
kie-media doctor --json
kie-media project init ./spot/project.json "A three-scene launch spot for the supplied product" --shots 3 --aspect-ratio 9:16 --json
kie-media project entity ./spot/project.json product ./product.png --description "Preserve the blue bottle, white label and cap" --json
kie-media project edit ./spot/project.json scene-1 --entity product --prompt "Wide product hero on a warm studio table" --narration "Your approved opening sentence." --json
kie-media project edit ./spot/project.json scene-2 --entity product --prompt "Close detail of the same bottle" --motion "Slow camera orbit, stable product geometry" --narration "Your approved detail sentence." --json
kie-media project edit ./spot/project.json scene-3 --entity product --prompt "Closing hero frame with clear space for the message" --narration "Your approved closing sentence." --json
kie-media project configure ./spot/project.json --music-prompt "Warm minimal ambient music, gentle pulse, instrumental" --json
kie-media project plan ./spot/project.json --json
```

The initial three shots are editable suggestions, not a finished creative treatment. Refine their purpose, visuals, motion and narration from the user's brief. Keep facts and product claims grounded. Narration is optional; empty narration means no TTS job. Music is optional. `--voice` sets an explicit documented voice ID; otherwise the selected TTS contract's default applies. Image/video/voice/music models can be configured explicitly.

Adding an entity only adds it to the library. Assign it to each relevant scene with `project edit ... --entity name` (repeat the flag for multiple entities). An empty entity list means no reference. References are copied locally and hashed. This is reference guidance, not trained identity or guaranteed consistency.

## Produce and review

```bash
kie-media project run ./spot/project.json --phase images --max-jobs 3 --json
kie-media project storyboard ./spot/project.json --json
kie-media project review ./spot/project.json scene-1.image accepted --note "Inspected: bottle shape, label and composition match" --json
# Inspect and review scene-2.image and scene-3.image as well.
kie-media project run ./spot/project.json --phase videos --max-jobs 3 --json
kie-media project run ./spot/project.json --phase audio --max-jobs 4 --json
```

Inspect generated files; listen to speech/music. Record an accepted or rejected review for each actual result with a concrete note. Review is work the host agent can perform when it has the relevant tools; it is not an extra user-approval ceremony. Never record an inspection that did not happen. If the host cannot inspect a required modality, report that boundary.

Video generation requires an accepted, unchanged image for that scene. Final rendering requires accepted, unchanged video and any requested audio. A rejection does not launch a paid retry. Correct the shot specification or explicitly increase its `--take` for a new image/video attempt within the user's scope.

`--max-jobs` limits new submissions in the requested phase. `--phase all` validates and budgets all remaining stages before starting and stops at review boundaries. Known tasks are polled again; they are never recreated just because polling/download was interrupted. A crash with no recorded task ID returns `needs_recovery`; inspect provider/history and use `project recover ... --task-id ...` only with the corresponding verified task. There is no force-retry of an unknown submission.

## Assemble

```bash
kie-media project render ./spot/project.json --captions --json
kie-media project report ./spot/project.json --json
```

FFmpeg and ffprobe are required only for import/technical checks/render. The renderer normalizes aspect ratio, frame rate and audio, concatenates scenes and mixes a quiet soundtrack. With narration it replaces the clip's own audio; without narration it keeps native clip audio. Narration is not cut to fit: the last video frame is held if necessary, with a warning. Captions are aligned to scenes, not individual words. Technical duration/stream checks do not replace visual and listening review. Report actual output files and remaining review limitations.

## Selective changes

```bash
kie-media project edit ./spot/project.json scene-2 --motion "A tighter, slow dolly-in" --dry-run --json
kie-media project edit ./spot/project.json scene-2 --motion "A tighter, slow dolly-in" --json
kie-media project run ./spot/project.json --phase videos --max-jobs 1 --json
```

The impact preview reports affected stages before mutation. A motion edit invalidates that video and final assembly. A visual/reference edit invalidates that image and its video. A narration edit invalidates that voice and assembly. Unchanged receipts and media remain reusable. Re-review changed outputs before rendering the updated film.

## Existing assets and handoff

```bash
kie-media project import ./spot/project.json scene-1.video ./approved-clip.mp4 --json
kie-media project export ./spot/project.json ./spot-handoff.zip --json
```

Imports are explicitly labeled imported, never provider-generated. Review them as usual. A complete imported video is a self-contained source: its upstream image is reported as `not_required_imported_video` and is not generated by `run`. Generated videos still require their reviewed image dependency. Export includes the project, referenced assets, hashes and receipts; it refuses changed assets and active/ambiguous jobs. Extract into a new folder to continue. Keep a single active working copy: exporting does not establish distributed locks between different computers. The report includes known cost totals and how many jobs lack cost observations; do not present a partial sum as the complete bill.

## Current limits

- The public KIE index checked on 2026-09-22 did not expose a verified 3D mesh-generation contract. Do not present three-scene video as true 3D.
- Schema validation is not a live quality/reliability certification. `catalog audit` reports unsupported/unavailable documents explicitly.
- No hard currency/credit ceiling is promised without authoritative pricing. Job limits are enforced.
- No automatic publishing. No universal visual-identity or virality guarantee.

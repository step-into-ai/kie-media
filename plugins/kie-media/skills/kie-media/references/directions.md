# Three creative directions, one selected film

Use this for comparing visual treatments of the same brief and selecting a different treatment per scene. It creates ordinary, editable project files. It does not spawn three LLM personas or generate media automatically.

## Create the alternatives

Start from an existing scene project whose brief, narration, subject references and timing are set:

```bash
kie-media project directions ./spot/project.json --output-dir ./ideas --json
kie-media project compare ./ideas/directions.json --json
```

The three initial visual directions are `calm`, `playful` and `dramatic`. They append different lighting/composition and camera briefs. They preserve narration, timing, model choices, voices, music and assigned references. These are starting points: read and improve the scene prompts using the normal `project edit` command when the user's brief calls for more distinctive treatments.

The original project is unchanged. Each direction has its own ID, journal and asset copies. Active or ambiguous jobs block branching; finish/recover them first. The collection directory must be new, so an existing set of ideas cannot be silently overwritten.

## Generate image previews first

Creating directions and comparing/selecting them is free. Actual media requests remain explicit:

```bash
kie-media project run ./ideas/calm/project.json --phase images --max-jobs 3 --json
kie-media project run ./ideas/playful/project.json --phase images --max-jobs 3 --json
kie-media project run ./ideas/dramatic/project.json --phase images --max-jobs 3 --json
kie-media project compare ./ideas/directions.json --json
```

For three scenes these commands can submit **nine image jobs in total**. Inspect the returned `new_image_jobs` and the user's authorized scope before production. There is no claim that the chosen image model is the cheapest; explicit models remain unchanged. Do not animate all variants merely because they exist.

The comparison HTML shows scene rows and three direction cards, with current images/clips or a clear pending placeholder. A selector on each row lets the user download `selection.json`. Selection is not visual approval: inspect results and record reviews on the relevant direction project before downstream generation.

## Compose the chosen scenes

Either use the comparison's selection file or explicit picks:

```bash
kie-media project compose ./ideas/directions.json --pick scene-1=calm --pick scene-2=playful --pick scene-3=dramatic --output ./winner/project.json --dry-run --json
kie-media project compose ./ideas/directions.json --selection-file ./selection.json --output ./winner/project.json --dry-run --json
```

Specify exactly one direction for every scene. The dry run reports new jobs, pending stages and reused stages, without creating the winner directory. Use the same command without `--dry-run` to write the winner.

Successful, unchanged assets retain their provider task IDs, reviews, hashes and source provenance. A selected unreviewed asset remains unreviewed; a rejected or failed asset cannot be turned into an accepted result by composition. Corrupted/missing assets block selection. Selected projects must agree on model settings, format, voice and music. Conflicting references with the same entity name also block selection; align the references before generating or selecting.

Unchanged narration can be reused across visual directions. The soundtrack is reused only when its contract, including total duration, matches the selected timeline. Otherwise it is reported as pending. The project report distinguishes inherited observed costs from new costs; copying a paid receipt does not charge again.

## Finish only the winner

```bash
kie-media project plan ./winner/project.json --json
kie-media project run ./winner/project.json --phase videos --max-jobs 3 --json
# Generate any missing voice/music, inspect the results and record reviews.
kie-media project render ./winner/project.json --captions --json
```

The winner is a normal independent project: edit, render and export it with existing commands. Its copied assets do not depend on the source folders remaining unchanged. Keep one active working copy of each project; this is not a distributed job scheduler.

## Demonstration

Show the same product in three different visual treatments. Choose a calm opening, a playful detail scene and a dramatic ending. Show the dry-run job count, then the selected project. The strongest proof is unchanged task IDs and hashes for reused scenes and no new charge for copied receipts. Do not call the initial text briefs rendered videos or claim automatic continuity/vision approval.

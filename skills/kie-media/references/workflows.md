# Workflows

## image
One or more independent image stages. Quality defaults to GPT Image 2; references or fast mode select Nano Banana 2 Lite.

## video
One stage per requested clip. Quality selects Seedance 2; fast mode selects Seedance 2 Fast. Supplied images are preserved as Seedance reference images. Product-video wording routes here before static product photography.

## image-to-video
Requires one still. Uses Kling 3 Turbo Image with a motion-only prompt. Missing media is a blocker, never a reason to fall back to text-to-video.

## product-photoshoot
Requires a product reference. Modes: `product_shot`, `lifestyle_scene`, `closeup_product_with_person`, `moodboard_pin`, `hero_banner`, `social_carousel`, `ad_creative_pack`, `virtual_model_tryout`, `conceptual_product`, `restyle`.

Format tie-breakers win: Pinterest → pin; hero/banner → hero; carousel → carousel. KIE templates are independent and always preserve supplied packaging identity.

## marketplace-cards
Requires a product image. Scopes: `main` (1), `product-images` (6), `aplus` (8), `full-set` (13). The default `agent run` cap blocks scopes above five jobs until `--max-jobs` is raised explicitly. Never fabricate product claims, ratings, badges, studies or endorsements.

## campaign
Generates the requested candidate count and stops at a blocking review stage. If animation was requested, the plan also contains one post-review `generate-selected` stage. Use vision, then resume the same manifest with `--selected-file`; only a candidate recorded by that manifest is accepted.

## video-explainer
Currently `hybrid`, not executable. The planner exposes research, script, audio, clips and assembly phases plus missing audio/voice/timeline capabilities. Never return loose clips as if they were a complete narrated explainer.

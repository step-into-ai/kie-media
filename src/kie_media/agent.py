from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class PlanError(ValueError):
    pass


@dataclass
class AgentStage:
    id: str
    role: str
    action: str
    description: str
    model: str | None = None
    prompt: str = ""
    asset: str | None = None
    command: list[str] | None = None
    depends_on: list[str] = field(default_factory=list)
    blocking: bool = False


@dataclass
class ProductionPlan:
    version: str
    workflow: str
    route_reason: str
    brief: str
    status: str
    executable: bool
    mode: str | None
    scope: str | None
    aspect_ratio: str
    duration: int | None
    count: int
    budget: str
    output_dir: str
    required_inputs: list[str]
    missing_inputs: list[str]
    assumptions: list[str]
    capability_gaps: list[str]
    stages: list[AgentStage]

    @property
    def estimated_jobs(self) -> int:
        return sum(stage.action in {"generate", "generate-selected"} and stage.command is not None for stage in self.stages)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["estimated_jobs"] = self.estimated_jobs
        return data


PRODUCT_MODES = {
    "product_shot": "clean catalog studio image, controlled softbox lighting, neutral background, accurate product geometry",
    "lifestyle_scene": "credible real-world lifestyle scene, natural interaction, atmospheric but product-led composition",
    "closeup_product_with_person": "tight editorial crop with hands or partial person demonstrating the product, product remains unobscured",
    "moodboard_pin": "vertical Pinterest-native composition, layered editorial moodboard energy, tactile details and save-worthy styling",
    "hero_banner": "wide campaign hero composition with clear negative space for optional web copy, strong focal hierarchy",
    "social_carousel": "coherent social carousel frame with a reusable visual system, strong single-message hierarchy",
    "ad_creative_pack": "performance-ad still with immediate hook, clear product focus, thumb-stopping composition",
    "virtual_model_tryout": "editorial model tryout showing fit and use accurately, believable materials and proportions",
    "conceptual_product": "premium conceptual CGI product scene, sculptural composition, controlled surrealism",
    "restyle": "preserve the subject and product identity exactly while changing only styling, palette, lighting and context",
}

MODE_ASPECT = {
    "moodboard_pin": "2:3",
    "hero_banner": "16:9",
    "social_carousel": "4:5",
    "ad_creative_pack": "4:5",
    "virtual_model_tryout": "4:5",
}

MARKETPLACE_SECONDARY = ["infographic", "multi_angle", "detail_shot", "lifestyle", "whats_in_box"]
MARKETPLACE_APLUS = [
    "aplus_hero_banner", "aplus_pain_points", "aplus_features", "aplus_ingredients",
    "aplus_efficacy", "aplus_how_to_use", "aplus_endorsement",
]

SUPPORTED_WORKFLOWS = {
    "auto", "image", "video", "image-to-video", "product-photoshoot",
    "marketplace-cards", "video-explainer", "campaign",
}


def _clean(text: str) -> str:
    return " ".join(str(text).strip().split())


def _has(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _has_word(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) for term in terms)


def _route(brief: str) -> tuple[str, str]:
    text = brief.casefold()
    if _has(text, ("marketplace", "amazon", "listing", "a+", "produktkarte", "product card")):
        return "marketplace-cards", "marketplace/listing intent"
    if _has(text, ("explainer", "erklärvideo", "erklaervideo", "narrated", "faceless video", "document into a video")):
        return "video-explainer", "narrated explainer intent"
    if _has(text, ("campaign", "kampagne")) or (_has(text, ("best one", "besten", "top one")) and _has(text, ("animate", "animier"))):
        return "campaign", "multi-asset campaign intent"
    if _has(text, ("animate", "animier", "image-to-video", "photo into", "foto in", "bild in")):
        return "image-to-video", "animation of an existing still"
    if _has_word(text, ("video", "videos", "clip", "clips", "film", "motion", "kamerafahrt", "kamerafahrten", "camera move")):
        return "video", "video generation intent"
    product = _has_word(text, (
        "product", "produkt", "bottle", "flasche", "serum", "candle", "kerze",
        "packaging", "verpackung", "pinterest pin", "hero banner", "carousel",
        "try-on", "photoshoot", "shooting",
    ))
    if product:
        return "product-photoshoot", "brand/product visual intent"
    return "image", "general image generation intent"


def _product_mode(brief: str, explicit: str | None) -> str:
    if explicit:
        if explicit not in PRODUCT_MODES:
            raise PlanError(f"Unknown product mode: {explicit}")
        return explicit
    text = brief.casefold()
    # Output format wins over scene details, matching the public Higgsfield rules.
    if "pinterest" in text or re.search(r"\bpins?\b", text): return "moodboard_pin"
    if _has(text, ("hero", "banner", "header")): return "hero_banner"
    if _has(text, ("carousel", "karussell", "slides", "swipe")): return "social_carousel"
    if _has_word(text, ("ad", "ads", "ad pack", "paid social", "meta ad", "tiktok ad")): return "ad_creative_pack"
    if _has(text, ("try-on", "wearing", "getragen", "lookbook", "on body")): return "virtual_model_tryout"
    if _has(text, ("hands", "applying", "holding", "demonstrat", "closeup", "close-up")): return "closeup_product_with_person"
    if _has(text, ("levitat", "floating", "splash", "surreal", "cgi", "sculptural")): return "conceptual_product"
    if _has(text, ("restyle", "seasonal", "different vibe", "anderer look", "redo")): return "restyle"
    if _has(text, ("studio", "catalog", "katalog", "neutral", "white background", "shopify")): return "product_shot"
    return "lifestyle_scene"


def _marketplace_scope(brief: str, explicit: str | None) -> str:
    allowed = {"main", "product-images", "aplus", "full-set"}
    if explicit:
        if explicit not in allowed:
            raise PlanError(f"Unknown marketplace scope: {explicit}")
        return explicit
    text = brief.casefold()
    full_set_patterns = (
        r"\b(?:full|complete)\s+(?:marketplace|listing|set|bundle)\b",
        r"\b(?:komplett(?:e[nmrs]?)?|vollständig(?:e[nmrs]?)?)\s+(?:marketplace|listing|set|satz|paket)\b",
    )
    if any(re.search(pattern, text) for pattern in full_set_patterns): return "full-set"
    if _has(text, ("a+", "aplus")): return "aplus"
    if _has(text, ("secondary", "sekundär", "product images", "produktbilder")): return "product-images"
    return "main"


def _campaign_wants_animation(brief: str) -> bool:
    text = brief.casefold()
    intent = re.compile(
        r"(?<!\w)(?:animat(?:e|es|ed|ing)|animation(?:s|en)?|videos?|motion|animier\w*|bewegung(?:en)?)(?!\w)"
    )
    negation_tail = re.compile(
        r"(?:\bno\b|\bnot\b|\bnever\b|\bdon\s+t\b|\bdont\b|\bwithout\b|\bohne\b|\bkein\w*\b|\bnicht\b)"
        r"(?:\s+(?:any|a|an|the|create|make|generate|produce|turn|video|videos|motion|animation|animations|"
        r"or|and|oder|und)){0,4}\s*$"
    )
    for match in intent.finditer(text):
        before = re.sub(r"[^\w]+", " ", text[max(0, match.start() - 80):match.start()]).strip()
        after = text[match.end():match.end() + 12]
        if negation_tail.search(before):
            continue
        if re.search(r"(?:\bnon\s*)$", before) or re.match(r"\s*-?\s*free\b", after):
            continue
        return True
    return False


def _motion_prompt(brief: str) -> str:
    text = _clean(brief)
    motion_terms = ("pull", "push", "dolly", "pan", "zoom", "track", "orbit", "tilt", "camera", "beweg", "fahrt")
    if not _has(text.casefold(), motion_terms):
        text = f"Subtle controlled camera push-in with natural ambient motion. {text}"
    return _limit_prompt(f"MOTION: {text}. Preserve the source composition and subject identity. Smooth coherent movement, stable geometry, no sudden cuts.")


def _limit_prompt(prompt: str, max_words: int = 180) -> str:
    words = _clean(prompt).split()
    return " ".join(words[:max_words])


def _product_prompt(brief: str, mode: str, variant: int) -> str:
    angles = ["front three-quarter camera", "low hero angle", "overhead editorial angle", "tight detail framing", "environmental wide framing"]
    return _limit_prompt(
        f"BRIEF: {_clean(brief)}. MODE: {PRODUCT_MODES[mode]}. VARIANT: {angles[(variant - 1) % len(angles)]}. "
        "Treat attached images as the authoritative product reference. Preserve packaging geometry, colors, label layout and distinctive marks. "
        "Do not invent claims, certifications, prices, logos or unreadable pseudo-copy. Commercial photography, precise materials, clean edges."
    )


def _marketplace_prompt(brief: str, asset: str) -> str:
    rules = {
        "main_image": "single product, centered and fully visible, pure clean background, no props, no badges, no added text",
        "infographic": "clear benefit hierarchy with restrained callout zones; only use factual wording supplied in the brief",
        "multi_angle": "coherent multi-angle presentation with exact product geometry and consistent scale",
        "detail_shot": "macro detail showing a real material, control, texture or packaging feature",
        "lifestyle": "credible in-use lifestyle scene with product still dominant and easy to identify",
        "whats_in_box": "organized flat lay of only the supplied or explicitly described package contents",
        "aplus_hero_banner": "wide premium brand story banner with product-led composition and useful negative space",
        "aplus_pain_points": "visual problem-to-solution module without invented claims or fear language",
        "aplus_features": "structured feature module using only features explicitly stated in the brief",
        "aplus_ingredients": "ingredient/material module; never invent ingredients, quantities or certifications",
        "aplus_efficacy": "benefit visualization without fabricated percentages, studies or medical claims",
        "aplus_how_to_use": "simple sequential usage scene without adding unsupported instructions",
        "aplus_endorsement": "trust-oriented closing module without fake reviews, awards, experts or endorsements",
    }
    return _limit_prompt(
        f"MARKETPLACE ASSET: {asset}. BRIEF: {_clean(brief)}. COMPOSITION: {rules[asset]}. "
        "The attached image is the authoritative product reference. Preserve exact packaging identity and proportions. "
        "Marketplace-ready, legible hierarchy, no watermark, no invented claims, ratings, badges, prices or trademarks."
    )


def _command(
    model: str,
    prompt: str,
    output_dir: str,
    *,
    media: list[str] | None = None,
    media_flag: str = "--image",
    reference_videos: list[str] | None = None,
    reference_audio: list[str] | None = None,
    params: dict[str, Any] | None = None,
) -> list[str]:
    command = ["kie-media", "generate", model, "--prompt", prompt]
    for path in media or []:
        command += [media_flag, path]
    for path in reference_videos or []:
        command += ["--reference-video", path]
    for path in reference_audio or []:
        command += ["--reference-audio", path]
    for key, value in (params or {}).items():
        command += ["--param", f"{key}={json.dumps(value, ensure_ascii=False)}"]
    command += ["--output-dir", output_dir, "--json"]
    return command


def _generate_stage(
    stage_id: str,
    role: str,
    description: str,
    model: str,
    prompt: str,
    output_dir: str,
    *,
    media: list[str] | None = None,
    media_flag: str = "--image",
    reference_videos: list[str] | None = None,
    reference_audio: list[str] | None = None,
    params: dict[str, Any] | None = None,
    asset: str | None = None,
    depends_on: list[str] | None = None,
    action: str = "generate",
) -> AgentStage:
    return AgentStage(
        id=stage_id,
        role=role,
        action=action,
        description=description,
        model=model,
        prompt=prompt,
        asset=asset,
        command=_command(
            model, prompt, output_dir, media=media, media_flag=media_flag,
            reference_videos=reference_videos, reference_audio=reference_audio, params=params,
        ),
        depends_on=list(depends_on or []),
    )


def build_plan(
    brief: str,
    *,
    workflow: str = "auto",
    media: list[str] | None = None,
    reference_videos: list[str] | None = None,
    reference_audio: list[str] | None = None,
    count: int = 1,
    aspect_ratio: str | None = None,
    duration: int | None = None,
    budget: str = "quality",
    output_dir: str | None = None,
    mode: str | None = None,
    scope: str | None = None,
) -> ProductionPlan:
    brief = _clean(brief)
    if not brief:
        raise PlanError("brief cannot be empty")
    if workflow not in SUPPORTED_WORKFLOWS:
        raise PlanError(f"Unknown workflow: {workflow}")
    if budget not in {"quality", "fast"}:
        raise PlanError("budget must be quality or fast")
    if not 1 <= count <= 20:
        raise PlanError("count must be from 1 to 20")
    media = list(media or [])
    reference_videos = list(reference_videos or [])
    reference_audio = list(reference_audio or [])
    selected, reason = _route(brief) if workflow == "auto" else (workflow, "explicit workflow")
    if selected != "video" and (reference_videos or reference_audio):
        raise PlanError("Video/audio reference inputs are only supported by the video workflow")
    if duration is not None:
        if selected == "video" and not 4 <= duration <= 15:
            raise PlanError("video duration must be from 4 to 15 seconds for the selected Seedance workflow")
        if selected in {"image-to-video", "campaign"} and not 3 <= duration <= 15:
            raise PlanError("animation duration must be from 3 to 15 seconds for the selected Kling workflow")
        if selected == "video-explainer" and not 10 <= duration <= 600:
            raise PlanError("explainer duration must be from 10 to 600 seconds")
    root = str(_canonical_path(output_dir or f"./kie-media-output/{selected}"))
    missing: list[str] = []
    required: list[str] = []
    assumptions: list[str] = []
    gaps: list[str] = []
    stages: list[AgentStage] = []
    chosen_mode: str | None = None
    chosen_scope: str | None = None
    chosen_aspect = aspect_ratio or "1:1"
    chosen_duration = duration

    if selected == "image":
        chosen_aspect = aspect_ratio or "1:1"
        has_reference = bool(media)
        text_sensitive = _has(brief.casefold(), ("text", "typography", "schrift", "poster", "logo", "headline"))
        model_name = "image-fast" if budget == "fast" or has_reference else "image-default"
        if text_sensitive and not has_reference:
            model_name = "image-default"
        for index in range(1, count + 1):
            prompt = _limit_prompt(f"{brief}. Variant {index}: deliberate composition, coherent lighting, clean details, no watermark.")
            params = {"aspect_ratio": chosen_aspect}
            if model_name == "image-default": params["resolution"] = "1K"
            stages.append(_generate_stage(f"image-{index}", "image-producer", "Generate image variant", model_name, prompt, root, media=media, params=params))
        if not aspect_ratio: assumptions.append("square 1:1 output")

    elif selected == "video":
        chosen_aspect = aspect_ratio or "16:9"
        chosen_duration = duration or 5
        model_name = "video-fast" if budget == "fast" else "video-default"
        for index in range(1, count + 1):
            prompt = _motion_prompt(f"{brief}. Motion variant {index} with a distinct but coherent camera treatment.")
            stages.append(_generate_stage(
                f"video-{index}", "video-producer", f"Generate requested video variant {index}", model_name, prompt, root,
                media=media, media_flag="--reference-image",
                reference_videos=reference_videos, reference_audio=reference_audio,
                params={"aspect_ratio": chosen_aspect, "duration": chosen_duration, "resolution": "720p"},
            ))
        if not duration: assumptions.append("five-second clip")

    elif selected == "image-to-video":
        required.append("reference_image")
        chosen_aspect = aspect_ratio or "source"
        chosen_duration = duration or 5
        if not media:
            missing.append("reference_image")
        else:
            prompt = _motion_prompt(brief)
            stages.append(_generate_stage(
                "animate-1", "video-producer", "Animate the supplied still", "video-kling-image", prompt, root,
                media=[media[0]], params={"duration": chosen_duration, "resolution": "720p"},
            ))
        if not duration: assumptions.append("five-second animation")

    elif selected == "product-photoshoot":
        required.append("product_image")
        chosen_mode = _product_mode(brief, mode)
        chosen_aspect = aspect_ratio or MODE_ASPECT.get(chosen_mode, "1:1")
        if not media:
            missing.append("product_image")
        else:
            for index in range(1, count + 1):
                prompt = _product_prompt(brief, chosen_mode, index)
                stages.append(_generate_stage(
                    f"product-{index}", "image-producer", f"Create {chosen_mode} variant {index}", "image-fast", prompt, root,
                    media=media, params={"aspect_ratio": chosen_aspect}, asset=chosen_mode,
                ))
        if count == 1: assumptions.append("one product visual")

    elif selected == "marketplace-cards":
        required.append("product_image")
        chosen_scope = _marketplace_scope(brief, scope)
        chosen_aspect = aspect_ratio or "1:1"
        if not media:
            missing.append("product_image")
        else:
            assets = ["main_image"]
            if chosen_scope in {"product-images", "full-set"}: assets += MARKETPLACE_SECONDARY
            if chosen_scope in {"aplus", "full-set"}: assets += MARKETPLACE_APLUS
            for index, asset in enumerate(assets, 1):
                asset_aspect = chosen_aspect
                if asset.startswith("aplus_"): asset_aspect = "16:9"
                prompt = _marketplace_prompt(brief, asset)
                stages.append(_generate_stage(
                    f"marketplace-{index:02d}", "image-producer", f"Create marketplace asset: {asset}", "image-fast", prompt, root,
                    media=media, params={"aspect_ratio": asset_aspect}, asset=asset,
                ))

    elif selected == "campaign":
        chosen_aspect = aspect_ratio or "4:5"
        image_model = "image-fast" if media or budget == "fast" else "image-default"
        image_ids: list[str] = []
        for index in range(1, count + 1):
            stage_id = f"campaign-image-{index}"
            image_ids.append(stage_id)
            prompt = _limit_prompt(
                f"CAMPAIGN BRIEF: {brief}. Creative route {index}: distinct composition and hook while keeping one coherent visual system. "
                "Production-ready campaign still, precise subject identity, clean details, no watermark."
            )
            params = {"aspect_ratio": chosen_aspect}
            if image_model == "image-default": params["resolution"] = "1K"
            stages.append(_generate_stage(stage_id, "image-producer", "Generate campaign candidate", image_model, prompt, root, media=media, params=params))
        stages.append(AgentStage(
            id="campaign-review", role="reviewer", action="review",
            description="Inspect all candidates, score prompt fidelity, identity, composition and defects, then select the strongest asset before animation.",
            depends_on=image_ids, blocking=True,
        ))
        wants_animation = _campaign_wants_animation(brief)
        if wants_animation:
            chosen_duration = duration or 5
            animation_prompt = _motion_prompt(
                "Animate the selected campaign winner with a subtle premium reveal and coherent camera movement"
            )
            stages.append(_generate_stage(
                "campaign-animation", "video-producer", "Animate only the visually selected campaign winner",
                "video-kling-image", animation_prompt, root, media=["{{selected_file}}"],
                params={"duration": chosen_duration, "resolution": "720p"},
                asset="selected_animation", depends_on=["campaign-review"], action="generate-selected",
            ))
            assumptions.append("animation waits for a visual review selection to avoid wasting credits")
        else:
            assumptions.append("visual review selects the strongest campaign candidate for delivery")

    elif selected == "video-explainer":
        chosen_aspect = aspect_ratio or "16:9"
        chosen_duration = duration or 60
        gaps = ["audio_generation", "voice_catalog", "timeline_assembly", "subtitle_burn_in"]
        assumptions += ["one-minute duration" if duration is None else f"{duration}-second duration", "non-photoreal illustrated style"]
        stages = [
            AgentStage("research", "creative-director", "research", "Verify factual inputs and create a sources list", blocking=True),
            AgentStage("script", "prompt-engineer", "script", "Write fixed ten-second narration and visual blocks", depends_on=["research"], blocking=True),
            AgentStage("audio", "audio-producer", "external", "Generate one narration take per block with an external TTS/audio provider", depends_on=["script"], blocking=True),
            AgentStage("clips", "video-producer", "external", "Generate matching KIE video clips after a universal style key exists", depends_on=["script", "audio"], blocking=True),
            AgentStage("assemble", "delivery-operator", "external", "Assemble ordered audio/video pairs and optional subtitles", depends_on=["clips"], blocking=True),
        ]

    status = "hybrid" if gaps else ("needs_input" if missing else "ready")
    executable = status == "ready" and any(stage.command for stage in stages)
    return ProductionPlan(
        version="1.0", workflow=selected, route_reason=reason, brief=brief,
        status=status, executable=executable, mode=chosen_mode, scope=chosen_scope,
        aspect_ratio=chosen_aspect, duration=chosen_duration, count=count, budget=budget,
        output_dir=root, required_inputs=required, missing_inputs=missing,
        assumptions=assumptions, capability_gaps=gaps, stages=stages,
    )


def _default_runner(command: list[str]) -> dict[str, Any]:
    if not command or command[0] != "kie-media":
        raise PlanError("agent stages may only execute kie-media commands")
    argv = [sys.executable, "-m", "kie_media.cli", *command[1:]]
    completed = subprocess.run(argv, text=True, capture_output=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise PlanError(f"Agent stage failed: {detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PlanError("Agent stage returned non-JSON output") from exc
    if not isinstance(value, dict):
        raise PlanError("Agent stage returned an unexpected result shape")
    return value


def execute_plan(
    plan: ProductionPlan,
    *,
    runner: Callable[[list[str]], dict[str, Any]] | None = None,
    prior_execution: dict[str, Any] | None = None,
    selected_file: str | None = None,
    checkpoint: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if plan.status != "ready" or not plan.executable:
        details = ", ".join(plan.missing_inputs or plan.capability_gaps) or plan.status
        raise PlanError(f"Plan is not executable: {details}")
    run = runner or _default_runner
    execution = copy.deepcopy(prior_execution) if prior_execution else {
        "state": "running", "running_stage": None, "results": [],
    }
    results = execution.setdefault("results", [])
    if not isinstance(results, list):
        raise PlanError("Prior execution results must be a list")
    if selected_file:
        if not prior_execution or prior_execution.get("state") != "awaiting_review":
            raise PlanError("--selected-file requires an awaiting-review manifest")
        generated_files = {
            value
            for item in results if isinstance(item, dict)
            for value in item.get("files", []) if isinstance(value, str)
        }
        if selected_file not in generated_files:
            raise PlanError("Selected file is not one of this manifest's generated candidates")
    completed = {
        item.get("stage_id") for item in results
        if isinstance(item, dict)
        and str(item.get("state", "")).casefold() in {"success", "completed", "complete", "succeeded"}
    }
    running_stage = execution.get("running_stage")
    if running_stage and running_stage not in completed:
        return {
            **execution,
            "state": "needs_recovery",
            "running_stage": running_stage,
            "error": execution.get("error")
            or "A paid stage may have been interrupted; inspect history/task status before resuming.",
        }
    if execution.get("state") == "completed":
        return execution

    def persist(*, after_paid: bool = False) -> bool:
        if checkpoint is None:
            return True
        try:
            checkpoint(copy.deepcopy(execution))
            return True
        except Exception as exc:
            execution.update({
                "state": "checkpoint_failed",
                "running_stage": None,
                "checkpoint_after_paid": after_paid,
                "error": f"{type(exc).__name__}: {exc}",
            })
            return False

    execution.update({"state": "running", "running_stage": None})
    if not persist():
        return execution

    for stage in plan.stages:
        if stage.id in completed:
            continue
        if stage.action == "review" and stage.blocking:
            if selected_file:
                execution.update({"state": "running", "blocked_on": None, "selected_file": selected_file})
                if not persist():
                    return execution
                continue
            execution.update({"state": "awaiting_review", "blocked_on": stage.id, "running_stage": None})
            persist()
            return execution
        if stage.command is None:
            if stage.blocking:
                execution.update({"state": "blocked", "blocked_on": stage.id, "running_stage": None})
                persist()
                return execution
            continue

        command = list(stage.command)
        if stage.action == "generate-selected":
            if not selected_file:
                execution.update({"state": "awaiting_review", "blocked_on": "campaign-review", "running_stage": None})
                persist()
                return execution
            command = [selected_file if value == "{{selected_file}}" else value for value in command]

        execution.update({"state": "running", "running_stage": stage.id, "blocked_on": None})
        if not persist():
            return execution
        try:
            result = run(command)
        except Exception as exc:
            execution.update({
                "state": "failed",
                "failed_stage": stage.id,
                # Keep the stage marker: creation may have succeeded before an
                # ambiguous network/process failure, so automatic resume must stop.
                "running_stage": stage.id,
                "error": f"{type(exc).__name__}: {exc}",
            })
            persist()
            return execution

        results.append({"stage_id": stage.id, "asset": stage.asset, **result})
        execution.update({"running_stage": None})
        if str(result.get("state", "")).casefold() not in {"success", "completed", "complete", "succeeded"}:
            execution.update({
                "state": "failed",
                "failed_stage": stage.id,
                "error": str(result.get("fail_message") or result.get("error") or "stage did not succeed"),
            })
            persist(after_paid=True)
            return execution
        completed.add(stage.id)
        if not persist(after_paid=True):
            return execution

    execution.update({"state": "completed", "running_stage": None, "blocked_on": None})
    persist()
    return execution


def plan_fingerprint(plan: ProductionPlan) -> str:
    encoded = json.dumps(
        plan.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def load_manifest(path: str | Path) -> dict[str, Any]:
    target = _canonical_path(path)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError(f"Cannot read agent manifest {target}: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("plan"), dict) or not isinstance(value.get("execution"), dict):
        raise PlanError(f"Invalid agent manifest: {target}")
    return value


def new_manifest_path(plan: ProductionPlan) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _canonical_path(plan.output_dir) / f"agent-run-{stamp}-{uuid.uuid4().hex[:8]}.json"


@contextmanager
def manifest_lock(path: str | Path):
    target = _canonical_path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = Path(f"{target}.lock")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PlanError(f"Agent manifest is already running: {target}") from exc
        yield target
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


@contextmanager
def production_lock(plan: ProductionPlan):
    lock_dir = _canonical_path(plan.output_dir) / ".kie-media-locks"
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(lock_dir, 0o700)
    lock_target = lock_dir / f"plan-{plan_fingerprint(plan)}"
    with manifest_lock(lock_target):
        yield lock_target


def save_manifest(path: str | Path, plan: ProductionPlan, execution: dict[str, Any]) -> Path:
    target = _canonical_path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "plan_fingerprint": plan_fingerprint(plan),
        "plan": plan.to_dict(),
        "execution": execution,
    }
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        os.chmod(target, 0o600)
    finally:
        temp.unlink(missing_ok=True)
    return target

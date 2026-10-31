"""Explicit, documented KIE adapters for video-recast requests.

These contracts are intentionally separate from the general static catalog.
They make the limits of Genjutsu-like workflows visible to the planner rather
than representing them as equivalent to Higgsfield's proprietary workflows.
"""
from __future__ import annotations

from typing import Any
import copy

from .models import FieldSpec, ModelSpec, ModelValidationError, prepare_model_input


_RECAST_SPECS = {
    "motion-transfer": ModelSpec(
        id="kling-3.0/motion-control",
        name="Kling 3.0 Motion Control",
        kind="video",
        description="Transfers a source performer's movement to one supplied subject image.",
        fields={
            "prompt": FieldSpec(str, required=True, max_length=2_500),
            "input_urls": FieldSpec(list, required=True, min_items=1, max_items=1),
            "video_urls": FieldSpec(list, required=True, min_items=1, max_items=1),
            "mode": FieldSpec(str, required=True),
            "character_orientation": FieldSpec(str, default="video", enum=("image", "video")),
        },
        docs="https://docs.kie.ai/market/kling/motion-control-v3",
    ),
    "object-swap": ModelSpec(
        id="wan/2-7-videoedit",
        name="Wan 2.7 Video Edit",
        kind="video",
        description="Prompt-directed source-video editing with one optional reference image.",
        fields={
            "prompt": FieldSpec(str, required=True, max_length=5_000),
            "negative_prompt": FieldSpec(str, default=""),
            "video_url": FieldSpec(str, required=True),
            "reference_image": FieldSpec(str),
            "resolution": FieldSpec(str, required=True),
            "aspect_ratio": FieldSpec(str),
            "duration": FieldSpec(int, default=0, minimum=0),
            "audio_setting": FieldSpec(str, default="auto", enum=("auto", "origin")),
            "prompt_extend": FieldSpec(bool, default=True),
            "watermark": FieldSpec(bool, default=False),
            "seed": FieldSpec(int, default=0, minimum=0),
        },
        docs="https://docs.kie.ai/market/wan/2-7-videoedit",
    ),
    "restyle": ModelSpec(
        id="kling-3.0-omni/transformation",
        name="Kling 3.0 Omni Transformation",
        kind="video",
        description="Transforms a source video from a prompt while retaining its movement direction.",
        fields={
            "prompt": FieldSpec(str, required=True, max_length=3_072),
            "video_urls": FieldSpec(list, required=True, min_items=1, max_items=1),
            "resolution": FieldSpec(str, required=True),
            "aspect_ratio": FieldSpec(str, default="auto"),
            "audio": FieldSpec(bool, default=False),
        },
        docs="https://docs.kie.ai/market/kling/v3-omni-transformation",
    ),
}


_CAPABILITIES = {
    "motion-transfer": {
        "model_id": "kling-3.0/motion-control",
        "source_min_seconds": 3,
        "source_max_seconds": 30,
        "max_reference_images": 1,
        "min_reference_images": 1,
        "resolutions": ["720p", "1080p"],
        "audio_preservation": "unsupported",
        "output_duration": "source_determined",
        "character_orientation": "video",
        "source_media": {
            "formats": ["mp4", "quicktime"], "max_bytes": 100_000_000,
            "min_dimension_px": 341, "max_dimension_px": None,
            "min_ratio": 0.4, "max_ratio": 2.5,
        },
        "reference_media": {
            "formats": ["jpeg", "jpg", "png"], "max_bytes": 10_000_000,
            "min_dimension_px": 341, "max_dimension_px": None,
            "min_ratio": 0.4, "max_ratio": 2.5, "allow_alpha": True,
        },
        "docs": _RECAST_SPECS["motion-transfer"].docs,
        "limitations": [
            "source video and subject image must show a clear head, shoulders, and torso",
            "source-video audio preservation is not documented for this model",
        ],
    },
    "object-swap": {
        "model_id": "wan/2-7-videoedit",
        "source_min_seconds": 2,
        "source_max_seconds": 10,
        "max_reference_images": 1,
        "min_reference_images": 1,
        "resolutions": ["720p", "1080p"],
        "audio_preservation": "origin_setting",
        "output_duration": "source_determined",
        "source_media": {"formats": ["mp4", "mov"], "max_bytes": 100_000_000, "min_dimension_px": 240, "max_dimension_px": 4096, "min_ratio": 0.125, "max_ratio": 8.0},
        "reference_media": {"formats": ["jpg", "png", "webp"], "max_bytes": None, "min_dimension_px": 240, "max_dimension_px": 8000, "min_ratio": 0.125, "max_ratio": 8.0, "allow_alpha": False},
        "docs": _RECAST_SPECS["object-swap"].docs,
        "limitations": [
            "reference image guides an edit but the documented API provides no object mask or tracking control",
            "`audio_setting=origin` requests preservation of the original audio",
        ],
    },
    "restyle": {
        "model_id": "kling-3.0-omni/transformation",
        "source_min_seconds": 3,
        "source_max_seconds": 15.5,
        "max_reference_images": 0,
        "min_reference_images": 0,
        "resolutions": ["720p", "1080p", "4k"],
        "audio_preservation": "unsupported",
        "output_duration": "source_determined",
        "source_media": {"formats": ["mp4", "mov"], "max_bytes": 200_000_000, "min_dimension_px": 700, "max_dimension_px": 4553, "min_ratio": 0.4, "max_ratio": 2.0, "max_pixels": 8_294_400, "min_fps": 24, "max_fps": 60},
        "reference_media": {"provider_support": "yes", "selected_adapter": "none"},
        "docs": _RECAST_SPECS["restyle"].docs,
        "limitations": [
            "this adapter intentionally takes no replacement references, although the provider has a separate reference branch",
            "source-video audio preservation is not documented for this model",
        ],
    },
}


def recast_capabilities(mode: str) -> dict[str, Any]:
    """Return declarative known limits for one supported mode."""
    try:
        return copy.deepcopy(_CAPABILITIES[mode])
    except KeyError as exc:
        choices = ", ".join(sorted(_CAPABILITIES))
        raise ModelValidationError(f"Unsupported recast mode {mode!r}; choose one of: {choices}") from exc


def prepare_recast_request(
    mode: str,
    prompt: str,
    *,
    video: str,
    references: list[str],
    duration: int,
    resolution: str,
    keep_original_sound: bool,
) -> tuple[ModelSpec, dict[str, Any]]:
    """Build a validated provider payload without uploading or creating a task.

    The duration argument records caller intent for planning. Each selected
    provider controls the output duration from its source/edit contract, so it
    is deliberately not sent where the public request example uses `0`.
    """
    if keep_original_sound and mode != "object-swap":
        raise ModelValidationError(
            f"{mode} does not document source-audio preservation; omit --keep-original-sound"
        )
    if not isinstance(duration, int) or isinstance(duration, bool) or duration < 1:
        raise ModelValidationError("duration must be a positive whole number")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ModelValidationError("prompt cannot be empty")
    if not isinstance(video, str) or not video.strip():
        raise ModelValidationError("A source video is required")
    if not isinstance(references, list) or any(not isinstance(item, str) or not item.strip() for item in references):
        raise ModelValidationError("references must be non-empty image URLs or paths")
    spec = _RECAST_SPECS.get(mode)
    if spec is None:
        recast_capabilities(mode)
        raise AssertionError("unreachable")
    capability = _CAPABILITIES[mode]
    minimum = capability["min_reference_images"]
    maximum = capability["max_reference_images"]
    if not minimum <= len(references) <= maximum:
        raise ModelValidationError(f"{mode} needs {minimum} to {maximum} reference image(s)")
    if resolution not in capability["resolutions"]:
        accepted = ", ".join(capability["resolutions"])
        raise ModelValidationError(f"{mode} supports only these documented resolutions: {accepted}")

    if mode == "motion-transfer":
        values = {
            "prompt": prompt,
            "input_urls": references,
            "video_urls": [video],
            "mode": resolution,
            # Follow the recommended orientation of the source performance.
            "character_orientation": "video",
        }
    elif mode == "object-swap":
        values = {
            "prompt": prompt,
            "video_url": video,
            "reference_image": references[0],
            "resolution": resolution,
            "duration": 0,
            "audio_setting": "origin" if keep_original_sound else "auto",
            "prompt_extend": True,
            "watermark": False,
            "seed": 0,
        }
    else:  # restyle
        values = {
            "prompt": prompt,
            "video_urls": [video],
            "resolution": resolution,
            "aspect_ratio": "auto",
            "audio": False,
        }
    return spec, prepare_model_input(spec, values)

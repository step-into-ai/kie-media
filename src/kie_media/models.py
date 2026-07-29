from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ModelValidationError(ValueError):
    pass


@dataclass(frozen=True)
class FieldSpec:
    type: type
    required: bool = False
    default: Any = None
    enum: tuple[Any, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    min_items: int | None = None
    max_items: int | None = None
    min_length: int | None = None
    max_length: int | None = None


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    kind: str
    description: str
    aliases: tuple[str, ...] = ()
    fields: dict[str, FieldSpec] = field(default_factory=dict)
    docs: str = ""


IMAGE_RATIOS = (
    "auto", "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5",
    "16:9", "9:16", "2:1", "1:2", "3:1", "1:3", "21:9", "9:21",
)
SEEDANCE_RATIOS = ("1:1", "4:3", "3:4", "16:9", "9:16", "21:9", "adaptive")


def _prompt(required: bool = True, max_length: int = 20_000) -> FieldSpec:
    return FieldSpec(str, required=required, max_length=max_length)


def _seedance_fields(resolutions: tuple[str, ...]) -> dict[str, FieldSpec]:
    return {
        "prompt": _prompt(max_length=5_000),
        "first_frame_url": FieldSpec(str),
        "last_frame_url": FieldSpec(str),
        "reference_image_urls": FieldSpec(list, max_items=9),
        "reference_video_urls": FieldSpec(list, max_items=3),
        "reference_audio_urls": FieldSpec(list, max_items=3),
        "return_last_frame": FieldSpec(bool, default=False),
        "generate_audio": FieldSpec(bool, default=True),
        "resolution": FieldSpec(str, default="720p", enum=resolutions),
        "aspect_ratio": FieldSpec(str, default="16:9", enum=SEEDANCE_RATIOS),
        "duration": FieldSpec(int, default=5, minimum=4, maximum=15),
        "web_search": FieldSpec(bool, default=False),
        "nsfw_checker": FieldSpec(bool, default=False),
    }


_MODELS = (
    ModelSpec(
        id="gpt-image-2-text-to-image", name="GPT Image 2", kind="image",
        description="High-fidelity image, design, typography and on-image text.",
        aliases=("image-default", "gpt-image-2"),
        fields={
            "prompt": _prompt(),
            "aspect_ratio": FieldSpec(str, default="auto", enum=IMAGE_RATIOS),
            "resolution": FieldSpec(str, default="1K", enum=("1K", "2K", "4K")),
        },
        docs="https://docs.kie.ai/market/gpt/gpt-image-2-text-to-image",
    ),
    ModelSpec(
        id="nano-banana-2-lite", name="Nano Banana 2 Lite", kind="image",
        description="Fast reference-driven image generation and edits.",
        aliases=("image-fast", "nano-banana-lite"),
        fields={
            "prompt": _prompt(),
            "image_urls": FieldSpec(list, default=[], max_items=10),
            "aspect_ratio": FieldSpec(
                str, default="auto",
                enum=("1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9", "auto"),
            ),
        },
        docs="https://docs.kie.ai/market/google/nano-banana-2-lite",
    ),
    ModelSpec(
        id="grok-imagine/text-to-image", name="Grok Imagine Image", kind="image",
        description="Bold and expressive image generation.",
        aliases=("image-bold", "grok-image"),
        fields={
            "prompt": _prompt(max_length=5_000),
            "aspect_ratio": FieldSpec(str, default="1:1", enum=("2:3", "3:2", "1:1", "16:9", "9:16")),
            "enable_pro": FieldSpec(bool, default=False),
            "nsfw_checker": FieldSpec(bool, default=False),
        },
        docs="https://docs.kie.ai/market/grok-imagine/text-to-image",
    ),
    ModelSpec(
        id="bytedance/seedance-2", name="Seedance 2", kind="video",
        description="Default serious video: cinematic, multimodal, multi-shot, up to 4K.",
        aliases=("video-default", "seedance-2"),
        fields=_seedance_fields(("480p", "720p", "1080p", "4k")),
        docs="https://docs.kie.ai/market/bytedance/seedance-2",
    ),
    ModelSpec(
        id="bytedance/seedance-2-fast", name="Seedance 2 Fast", kind="video",
        description="Fast Seedance 2 generation at 480p/720p.",
        aliases=("video-fast", "seedance-2-fast"),
        fields=_seedance_fields(("480p", "720p")),
        docs="https://docs.kie.ai/market/bytedance/seedance-2-fast",
    ),
    ModelSpec(
        id="kling/v3-turbo-text-to-video", name="Kling 3 Turbo Text", kind="video",
        description="Fast, lower-cost Kling text-to-video for simple shots.",
        aliases=("video-kling-fast", "kling-3-turbo"),
        fields={
            "prompt": _prompt(),
            "duration": FieldSpec(str, default="5"),
            "aspect_ratio": FieldSpec(str, default="16:9", enum=("1:1", "9:16", "16:9")),
            "resolution": FieldSpec(str, default="720p", enum=("720p", "1080p")),
        },
        docs="https://docs.kie.ai/market/kling/v3-turbo-text-to-video",
    ),
    ModelSpec(
        id="kling/v3-turbo-image-to-video", name="Kling 3 Turbo Image", kind="video",
        description="Fast animation from one start image.",
        aliases=("video-kling-image",),
        fields={
            "prompt": _prompt(),
            "duration": FieldSpec(str, default="5"),
            "resolution": FieldSpec(str, default="720p", enum=("720p", "1080p")),
            "image_urls": FieldSpec(list, required=True, min_items=1, max_items=1),
        },
        docs="https://docs.kie.ai/market/kling/v3-turbo-image-to-video",
    ),
    ModelSpec(
        id="grok-imagine/text-to-video", name="Grok Imagine Video", kind="video",
        description="Bold, stylized text-to-video with 6–30 second duration.",
        aliases=("video-bold", "grok-video"),
        fields={
            "prompt": _prompt(max_length=5_000),
            "aspect_ratio": FieldSpec(str, default="2:3", enum=("2:3", "3:2", "1:1", "16:9", "9:16")),
            "mode": FieldSpec(str, default="normal", enum=("fun", "normal", "spicy")),
            "duration": FieldSpec(int, default=6, minimum=6, maximum=30),
            "resolution": FieldSpec(str, default="480p", enum=("480p", "720p")),
            "nsfw_checker": FieldSpec(bool, default=False),
        },
        docs="https://docs.kie.ai/market/grok-imagine/text-to-video",
    ),
)

_BY_NAME = {key: model for model in _MODELS for key in (model.id, *model.aliases)}


def list_models(kind: str | None = None) -> list[ModelSpec]:
    return [model for model in _MODELS if kind is None or model.kind == kind]


def get_model(name: str) -> ModelSpec:
    model = _BY_NAME.get(name)
    if model:
        return model
    # Dynamic KIE documentation schemas are cached locally after discovery.
    # Import lazily so the static catalog remains dependency-light and never
    # performs network I/O merely because a model is inspected internally.
    try:
        from .catalog import DocsCatalog
        cached = DocsCatalog().cached_model(name)
        if cached:
            return cached
    except (OSError, ValueError):
        pass
    return ModelSpec(name, name, "custom", "Uncatalogued KIE model; input is passed through without local schema validation.")


def _coerce(value: Any, expected: type) -> Any:
    if isinstance(value, expected):
        return value
    if expected is bool and isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    if expected is int and isinstance(value, (str, float)):
        return int(value)
    if expected is float and isinstance(value, (str, int)):
        return float(value)
    if expected is str and isinstance(value, (str, int, float, bool)):
        return str(value)
    raise ModelValidationError(f"Expected {expected.__name__}, got {type(value).__name__}")


def _validate_cross_fields(model: ModelSpec, result: dict[str, Any]) -> None:
    if not str(result.get("prompt", "")).strip():
        raise ModelValidationError("prompt cannot be empty")
    if model.id == "gpt-image-2-text-to-image":
        resolution = result.get("resolution")
        aspect = result.get("aspect_ratio")
        if aspect == "auto" and resolution != "1K":
            raise ModelValidationError("GPT Image 2 with aspect_ratio=auto only supports resolution=1K")
        if resolution in {"2K", "4K"} and aspect in {"5:4", "4:5", "3:1", "1:3", "9:21"}:
            raise ModelValidationError(f"GPT Image 2 {resolution} does not support aspect_ratio={aspect}")
        if resolution == "4K" and aspect == "1:1":
            raise ModelValidationError("GPT Image 2 does not support 4K at aspect_ratio=1:1")
    if model.id.startswith("kling/v3-turbo-"):
        try:
            duration = int(result["duration"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelValidationError("Kling duration must be an integer from 3 to 15") from exc
        if not 3 <= duration <= 15:
            raise ModelValidationError("Kling duration must be from 3 to 15 seconds")
    if model.id.startswith("bytedance/seedance-2"):
        has_frames = bool(result.get("first_frame_url") or result.get("last_frame_url"))
        has_references = any(result.get(key) for key in ("reference_image_urls", "reference_video_urls", "reference_audio_urls"))
        if has_frames and has_references:
            raise ModelValidationError("Seedance frame mode and multimodal reference mode cannot be combined")
        if result.get("last_frame_url") and not result.get("first_frame_url"):
            raise ModelValidationError("Seedance last_frame_url requires first_frame_url")


def prepare_model_input(model: ModelSpec, values: dict[str, Any]) -> dict[str, Any]:
    if model.kind == "custom":
        if not str(values.get("prompt", "")).strip():
            raise ModelValidationError("prompt is required for uncatalogued models")
        return dict(values)
    unknown = set(values) - set(model.fields)
    if unknown:
        raise ModelValidationError(f"Unknown input parameter(s) for {model.id}: {', '.join(sorted(unknown))}")
    result: dict[str, Any] = {}
    for key, spec in model.fields.items():
        if key in values and values[key] is not None:
            value = _coerce(values[key], spec.type)
        elif spec.default is not None:
            value = list(spec.default) if isinstance(spec.default, list) else spec.default
        elif spec.required:
            raise ModelValidationError(f"Missing required input parameter: {key}")
        else:
            continue
        if spec.enum and value not in spec.enum:
            raise ModelValidationError(f"Invalid {key}={value!r}; choose one of: {', '.join(map(str, spec.enum))}")
        if spec.minimum is not None and value < spec.minimum:
            raise ModelValidationError(f"{key} must be >= {spec.minimum:g}")
        if spec.maximum is not None and value > spec.maximum:
            raise ModelValidationError(f"{key} must be <= {spec.maximum:g}")
        if spec.min_length is not None and isinstance(value, str) and len(value) < spec.min_length:
            raise ModelValidationError(f"{key} must contain at least {spec.min_length} characters")
        if spec.max_length is not None and isinstance(value, str) and len(value) > spec.max_length:
            raise ModelValidationError(f"{key} must contain at most {spec.max_length} characters")
        if spec.min_items is not None and isinstance(value, list) and len(value) < spec.min_items:
            raise ModelValidationError(f"{key} requires at least {spec.min_items} item(s)")
        if spec.max_items is not None and isinstance(value, list) and len(value) > spec.max_items:
            raise ModelValidationError(f"{key} accepts at most {spec.max_items} item(s)")
        result[key] = value
    _validate_cross_fields(model, result)
    return result


def prepare_input(model_name: str, values: dict[str, Any]) -> dict[str, Any]:
    return prepare_model_input(get_model(model_name), values)

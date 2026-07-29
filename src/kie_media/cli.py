from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .client import KieApiError, KieClient, TaskResult, parse_result, validate_wait_options
from .history import HistoryStore, default_home
from .models import ModelValidationError, get_model, list_models, prepare_input


def parse_key_values(items: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        if "=" not in item: raise ValueError(f"Expected KEY=VALUE, got: {item}")
        key, raw = item.split("=", 1)
        if not key: raise ValueError("Parameter name cannot be empty")
        try: value = json.loads(raw)
        except json.JSONDecodeError: value = raw
        result[key] = value
    return result


def _load_env_key(env_file: str | None = None) -> str | None:
    if os.environ.get("KIE_API_KEY"): return os.environ["KIE_API_KEY"]
    candidates = []
    if env_file: candidates.append(Path(env_file))
    if os.environ.get("KIE_MEDIA_ENV_FILE"): candidates.append(Path(os.environ["KIE_MEDIA_ENV_FILE"]))
    if os.environ.get("HERMES_HOME"): candidates.append(Path(os.environ["HERMES_HOME"]) / ".env")
    candidates += [Path.home() / ".hermes" / ".env", Path.cwd() / ".env"]
    for path in candidates:
        path = path.expanduser()
        if not path.is_file(): continue
        for line in path.read_text(errors="ignore").splitlines():
            if line.startswith("KIE_API_KEY="):
                value = line.partition("=")[2].strip().strip("\"'")
                if value: return value
    return None


def _add_output_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE", help="Model input; JSON values supported")
    parser.add_argument("--image", action="append", default=[], help="Image URL or local file (auto-uploaded)")
    parser.add_argument("--start-image", help="First frame URL or local file")
    parser.add_argument("--end-image", help="Last frame URL or local file")
    parser.add_argument("--reference-image", action="append", default=[], help="Reference image URL or local file")
    parser.add_argument("--reference-video", action="append", default=[], help="Reference video URL or local file")
    parser.add_argument("--reference-audio", action="append", default=[], help="Reference audio URL or local file")
    parser.add_argument("--callback-url")
    parser.add_argument("--wait", action="store_true", default=True, help="Wait for completion (default)")
    parser.add_argument("--no-wait", action="store_false", dest="wait")
    parser.add_argument("--wait-timeout", type=float, default=900)
    parser.add_argument("--wait-interval", type=float, default=2)
    parser.add_argument("--output-dir", help="Download directory; defaults to KIE Media asset store")
    parser.add_argument("--no-download", action="store_true", help="Keep remote URLs only")
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kie-media", description="Agent-friendly KIE.ai image and video generation")
    parser.add_argument("--env-file", help="Optional .env containing KIE_API_KEY")
    sub = parser.add_subparsers(dest="command", required=True)
    credits = sub.add_parser("credits", help="Show remaining KIE credits"); credits.add_argument("--json", action="store_true")
    models = sub.add_parser("models", help="List curated KIE models and aliases"); models.add_argument("--kind", choices=["image", "video"]); models.add_argument("--json", action="store_true")
    model = sub.add_parser("model", help="Inspect one model's local input schema"); model.add_argument("name"); model.add_argument("--json", action="store_true")
    upload = sub.add_parser("upload", help="Upload a local media file to KIE's temporary store"); upload.add_argument("path"); upload.add_argument("--json", action="store_true")
    generate = sub.add_parser("generate", help="Generate with a model or alias")
    generate.add_argument("model"); generate.add_argument("--prompt", required=True); _add_output_flags(generate)
    image = sub.add_parser("image", help="Generate an image with image-default")
    image.add_argument("prompt"); image.add_argument("--model", default="image-default"); image.add_argument("--aspect-ratio"); image.add_argument("--resolution"); _add_output_flags(image)
    video = sub.add_parser("video", help="Generate a video with video-default")
    video.add_argument("prompt"); video.add_argument("--model", default="video-default"); video.add_argument("--aspect-ratio"); video.add_argument("--resolution"); video.add_argument("--duration", type=int); _add_output_flags(video)
    for name in ("status", "wait", "download"):
        cmd = sub.add_parser(name, help=f"{name.title()} a KIE task"); cmd.add_argument("task_id"); cmd.add_argument("--json", action="store_true")
        if name == "wait": cmd.add_argument("--timeout", type=float, default=900); cmd.add_argument("--interval", type=float, default=2); cmd.add_argument("--output-dir"); cmd.add_argument("--no-download", action="store_true")
        if name == "download": cmd.add_argument("--output-dir")
    hist = sub.add_parser("history", help="Show local generation history"); hist.add_argument("--limit", type=int, default=20); hist.add_argument("--json", action="store_true")
    return parser


def _model_rows(kind: str | None) -> list[dict[str, Any]]:
    return [{"id": m.id, "name": m.name, "kind": m.kind, "aliases": list(m.aliases), "description": m.description, "docs": m.docs} for m in list_models(kind)]


def _model_detail(name: str) -> dict[str, Any]:
    model = get_model(name)
    return {
        "id": model.id,
        "name": model.name,
        "kind": model.kind,
        "aliases": list(model.aliases),
        "description": model.description,
        "docs": model.docs,
        "inputs": {
            key: {
                "type": spec.type.__name__,
                "required": spec.required,
                "default": spec.default,
                "enum": list(spec.enum),
                "minimum": spec.minimum,
                "maximum": spec.maximum,
                "min_items": spec.min_items,
                "max_items": spec.max_items,
                "max_length": spec.max_length,
            }
            for key, spec in model.fields.items()
        },
    }


def _result_dict(result: TaskResult, paths: list[str] | None = None) -> dict[str, Any]:
    return {"task_id": result.task_id, "model": result.model, "state": result.state, "urls": result.urls, "files": paths or [], "credits_consumed": result.credits_consumed, "fail_code": result.fail_code, "fail_message": result.fail_message}


def _print(value: Any, as_json: bool = False) -> None:
    if as_json: print(json.dumps(value, ensure_ascii=False, indent=2)); return
    if isinstance(value, dict):
        for key, item in value.items():
            if item not in (None, "", [], {}): print(f"{key}: {item}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict): print(f"{item.get('name', item.get('task_id', ''))}: {item}")
            else: print(item)
    else: print(value)


def _safe_history_append(history: HistoryStore, record: dict[str, Any]) -> bool:
    try:
        history.append(record)
        return True
    except Exception as exc:
        # History is secondary. Never hide or abandon a paid task because the
        # local state store is read-only/full; keep returning the task/result.
        task = f" task_id={record['task_id']}" if record.get("task_id") else ""
        print(f"warning: history write failed{task} ({type(exc).__name__}: {exc})", file=sys.stderr)
        return False


def _resolve_list(client: KieClient, values: list[str], expected_kind: str) -> list[str]:
    return [client.resolve_media(value, expected_kind) for value in values]


def _resolve_media_params(client: KieClient, values: dict[str, Any]) -> None:
    scalar_fields = {"first_frame_url": "image", "last_frame_url": "image"}
    list_fields = {
        "image_urls": "image", "reference_image_urls": "image",
        "reference_video_urls": "video", "reference_audio_urls": "audio",
    }
    for key, kind in scalar_fields.items():
        if key not in values: continue
        value = values[key]
        if not isinstance(value, str):
            raise ModelValidationError(f"{key} must be a media URL or local file path string")
        values[key] = client.resolve_media(value, kind)
    for key, kind in list_fields.items():
        if key not in values: continue
        items = values[key]
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            raise ModelValidationError(f"{key} must be a list of media URL/path strings")
        values[key] = _resolve_list(client, items, kind)


def _apply_media(client: KieClient, model_id: str, values: dict[str, Any], args: argparse.Namespace) -> None:
    model = get_model(model_id)
    requested = bool(args.image or args.start_image or args.end_image or args.reference_image or args.reference_video or args.reference_audio)
    if model_id in {"nano-banana-2-lite", "kling/v3-turbo-image-to-video"}:
        if args.end_image or args.reference_video or args.reference_audio:
            raise ModelValidationError(f"{model_id} only accepts image inputs")
    elif model_id.startswith("bytedance/seedance-2"):
        pass
    elif model.kind != "custom" and requested:
        raise ModelValidationError(f"{model_id} does not accept media input flags")
    if model_id.startswith("bytedance/seedance-2"):
        has_frames = bool(args.image or args.start_image or args.end_image)
        has_references = bool(args.reference_image or args.reference_video or args.reference_audio)
        if has_frames and has_references:
            raise ModelValidationError("Seedance frame mode and multimodal reference mode cannot be combined")
        if args.start_image and args.image:
            raise ModelValidationError("Use either --start-image or one --image for Seedance, not both")
        if len(args.image) > 1:
            raise ModelValidationError("Seedance frame mode accepts one --image; use --end-image for a final frame")
        if args.end_image and not (args.start_image or args.image):
            raise ModelValidationError("Seedance --end-image requires --start-image or --image")
    # Keep these values local/raw for static schema validation. Upload and URL
    # resolution happen only after every model and wait option is known valid.
    images = list(args.image)
    start = args.start_image
    end = args.end_image
    refs_img = list(args.reference_image)
    refs_vid = list(args.reference_video)
    refs_aud = list(args.reference_audio)
    if model_id in {"nano-banana-2-lite", "kling/v3-turbo-image-to-video"}:
        if start: images.insert(0, start)
        images.extend(refs_img)
        if images: values["image_urls"] = images
    elif model_id.startswith("bytedance/seedance-2"):
        if start or images: values["first_frame_url"] = start or images[0]
        if end: values["last_frame_url"] = end
        if refs_img: values["reference_image_urls"] = refs_img
        if refs_vid: values["reference_video_urls"] = refs_vid
        if refs_aud: values["reference_audio_urls"] = refs_aud
    elif model.kind == "custom":
        if images or start: values["image_urls"] = ([start] if start else []) + images
        if end: values["last_frame_url"] = end
        if refs_img: values["reference_image_urls"] = refs_img
        if refs_vid: values["reference_video_urls"] = refs_vid
        if refs_aud: values["reference_audio_urls"] = refs_aud


def _generate(client: KieClient, history: HistoryStore, args: argparse.Namespace, model_name: str, prompt: str, shortcut_values: dict[str, Any] | None = None, expected_kind: str | None = None) -> int:
    spec = get_model(model_name)
    if expected_kind and spec.kind != expected_kind:
        raise ModelValidationError(f"The {expected_kind} shortcut requires model kind {expected_kind}, got {spec.kind}: {spec.id}")
    values = parse_key_values(args.param)
    media_param_fields = {"first_frame_url", "last_frame_url", "image_urls", "reference_image_urls", "reference_video_urls", "reference_audio_urls"}
    has_media_flags = bool(args.image or args.start_image or args.end_image or args.reference_image or args.reference_video or args.reference_audio)
    if has_media_flags and set(values).intersection(media_param_fields):
        raise ModelValidationError("Do not mix media --param fields with dedicated media flags")
    shortcut_values = shortcut_values or {}
    if spec.kind != "custom":
        unknown_params = set(values) - set(spec.fields)
        if unknown_params:
            raise ModelValidationError(f"Unknown input parameter(s) for {spec.id}: {', '.join(sorted(unknown_params))}")
        unsupported_shortcuts = {key for key, value in shortcut_values.items() if value is not None and key not in spec.fields}
        if unsupported_shortcuts:
            raise ModelValidationError(f"Unsupported shortcut option(s) for {spec.id}: {', '.join(sorted(unsupported_shortcuts))}")
    if spec.kind == "custom":
        values.update({key: value for key, value in shortcut_values.items() if value is not None})
    else:
        values.update({key: value for key, value in shortcut_values.items() if key in spec.fields and value is not None})
    values["prompt"] = prompt
    _apply_media(client, spec.id, values, args)
    if args.wait:
        validate_wait_options(args.wait_timeout, args.wait_interval)
    # Static validation before any upload or paid task creation.
    prepare_input(spec.id, values)
    _resolve_media_params(client, values)
    input_data = prepare_input(spec.id, values)
    task_id, _ = client.create_task(spec.id, input_data, args.callback_url)
    _safe_history_append(history, {"task_id": task_id, "model": spec.id, "state": "submitted", "input": input_data})
    if not args.wait:
        _print({"task_id": task_id, "model": spec.id, "state": "submitted"}, args.json)
        return 0
    try:
        result = client.wait(task_id, timeout=args.wait_timeout, interval=args.wait_interval)
        paths: list[str] = []
        if result.urls and not args.no_download:
            output_dir = Path(args.output_dir).expanduser() if args.output_dir else default_home() / "assets"
            paths = client.download_urls(result.urls, output_dir, task_id=task_id)
        item = _result_dict(result, paths)
        _safe_history_append(history, item)
    except Exception as exc:
        _safe_history_append(history, {"task_id": task_id, "model": spec.id, "state": "error", "error": str(exc)})
        if isinstance(exc, KieApiError):
            raise KieApiError(f"Task {task_id}: {exc}", exc.code, exc.payload) from exc
        raise KieApiError(f"Task {task_id}: {exc}") from exc
    _print(item, args.json)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(); args = parser.parse_args(argv)
    try:
        if args.command == "models": _print(_model_rows(args.kind), args.json); return 0
        if args.command == "model": _print(_model_detail(args.name), args.json); return 0
        history = HistoryStore()
        if args.command == "history": _print(history.list(args.limit), args.json); return 0
        key = _load_env_key(args.env_file)
        client = KieClient(key or "")
        if args.command == "credits": _print({"credits": client.credits()}, args.json); return 0
        if args.command == "upload": _print({"file": str(Path(args.path).expanduser()), "url": client.upload_file(args.path)}, args.json); return 0
        if args.command == "generate": return _generate(client, history, args, args.model, args.prompt)
        if args.command == "image": return _generate(client, history, args, args.model, args.prompt, {"aspect_ratio": args.aspect_ratio, "resolution": args.resolution}, expected_kind="image")
        if args.command == "video": return _generate(client, history, args, args.model, args.prompt, {"aspect_ratio": args.aspect_ratio, "resolution": args.resolution, "duration": args.duration}, expected_kind="video")
        if args.command == "status":
            try: _print(_result_dict(parse_result(client.get_task(args.task_id))), args.json); return 0
            except KieApiError as exc: raise KieApiError(f"Task {args.task_id}: {exc}", exc.code, exc.payload) from exc
        if args.command == "wait":
            try:
                result = client.wait(args.task_id, timeout=args.timeout, interval=args.interval)
                paths = client.download_urls(result.urls, args.output_dir or default_home() / "assets", task_id=args.task_id) if result.urls and not args.no_download else []
                item = _result_dict(result, paths); _safe_history_append(history, item); _print(item, args.json); return 0
            except Exception as exc:
                _safe_history_append(history, {"task_id": args.task_id, "state": "error", "error": str(exc)})
                if isinstance(exc, KieApiError): raise KieApiError(f"Task {args.task_id}: {exc}", exc.code, exc.payload) from exc
                raise KieApiError(f"Task {args.task_id}: {exc}") from exc
        if args.command == "download":
            try:
                result = parse_result(client.get_task(args.task_id))
                if result.state not in {"success", "completed", "complete", "succeeded"}: raise KieApiError(f"not complete (state={result.state or 'unknown'})")
                paths = client.download_urls(result.urls, args.output_dir or default_home() / "assets", task_id=args.task_id)
                _print({"task_id": args.task_id, "files": paths, "urls": result.urls}, args.json); return 0
            except KieApiError as exc: raise KieApiError(f"Task {args.task_id}: {exc}", exc.code, exc.payload) from exc
        parser.error("unknown command")
    except (KieApiError, ModelValidationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

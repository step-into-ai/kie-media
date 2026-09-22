from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .agent import (
    PlanError, build_plan, execute_plan, load_manifest, manifest_lock, new_manifest_path,
    plan_fingerprint, production_lock, save_manifest,
)
from .client import KieApiError, KieClient, TaskResult, parse_result, validate_wait_options
from .catalog import CatalogError, DocsCatalog
from .history import HistoryStore, default_home
from .models import ModelSpec, ModelValidationError, get_model, list_models, prepare_model_input
from .preferences import Preferences, PreferencesError, PreferencesStore, TIERS


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


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


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


def _add_agent_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("brief")
    parser.add_argument(
        "--workflow", default="auto",
        choices=["auto", "image", "video", "image-to-video", "product-photoshoot", "marketplace-cards", "video-explainer", "campaign"],
    )
    parser.add_argument("--media", action="append", default=[], help="Reference/product image path; repeat for multiple images")
    parser.add_argument("--reference-video", action="append", default=[], help="Seedance reference video; repeat as needed")
    parser.add_argument("--reference-audio", action="append", default=[], help="Seedance reference audio; repeat as needed")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--aspect-ratio")
    parser.add_argument("--duration", type=int)
    parser.add_argument("--tier", choices=TIERS, help="Model strategy: budget, balanced or premium")
    parser.add_argument("--budget", choices=["quality", "fast"], help="Deprecated alias: fast=budget, quality=balanced")
    parser.add_argument("--image-model", help="Preferred image model name, alias or KIE model ID")
    parser.add_argument("--video-model", help="Preferred video model name, alias or KIE model ID")
    parser.add_argument("--no-preferences", action="store_true", help="Ignore saved local model preferences")
    parser.add_argument("--output-dir")
    parser.add_argument("--mode", help="Product-photoshoot mode")
    parser.add_argument("--scope", choices=["main", "product-images", "aplus", "full-set"])
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kie-media", description="Agent-friendly KIE.ai image and video generation")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--env-file", help="Optional .env containing KIE_API_KEY")
    sub = parser.add_subparsers(dest="command", required=True)
    credits = sub.add_parser("credits", help="Show remaining KIE credits"); credits.add_argument("--json", action="store_true")
    models = sub.add_parser("models", help="List curated models or search KIE's live documentation")
    models.add_argument("--kind", choices=["image", "video", "audio", "chat", "3d", "other"])
    models.add_argument("--live", action="store_true", help="Search the current KIE documentation index")
    models.add_argument("--search", default="", help="Filter live model documentation by name")
    models.add_argument("--refresh", action="store_true", help="Refresh the validated documentation cache")
    models.add_argument("--json", action="store_true")
    model = sub.add_parser("model", help="Inspect a curated, cached or live KIE model schema")
    model.add_argument("name"); model.add_argument("--kind", choices=["image", "video", "audio", "chat", "3d", "other"]); model.add_argument("--refresh", action="store_true"); model.add_argument("--json", action="store_true")
    preferences = sub.add_parser("preferences", help="Show or update private per-user model preferences")
    preference_sub = preferences.add_subparsers(dest="preferences_command", required=True)
    preference_show = preference_sub.add_parser("show"); preference_show.add_argument("--json", action="store_true")
    preference_set = preference_sub.add_parser("set")
    preference_set.add_argument("--tier", choices=TIERS)
    preference_set.add_argument("--image-model")
    preference_set.add_argument("--video-model")
    preference_set.add_argument("--clear-image-model", action="store_true")
    preference_set.add_argument("--clear-video-model", action="store_true")
    preference_set.add_argument("--exclude-model", action="append", default=[])
    preference_set.add_argument("--clear-exclusions", action="store_true")
    preference_set.add_argument("--max-jobs", type=_positive_int)
    preference_set.add_argument("--json", action="store_true")
    preference_reset = preference_sub.add_parser("reset"); preference_reset.add_argument("--json", action="store_true")
    upload = sub.add_parser("upload", help="Upload a local media file to KIE's temporary store"); upload.add_argument("path"); upload.add_argument("--json", action="store_true")
    generate = sub.add_parser("generate", help="Generate with a model or alias")
    generate.add_argument("model"); generate.add_argument("--prompt"); _add_output_flags(generate)
    image = sub.add_parser("image", help="Generate an image with image-default")
    image.add_argument("prompt"); image.add_argument("--model", default="image-default"); image.add_argument("--aspect-ratio"); image.add_argument("--resolution"); _add_output_flags(image)
    video = sub.add_parser("video", help="Generate a video with video-default")
    video.add_argument("prompt"); video.add_argument("--model", default="video-default"); video.add_argument("--aspect-ratio"); video.add_argument("--resolution"); video.add_argument("--duration", type=int); _add_output_flags(video)
    for name in ("status", "wait", "download"):
        cmd = sub.add_parser(name, help=f"{name.title()} a KIE task"); cmd.add_argument("task_id"); cmd.add_argument("--json", action="store_true")
        if name == "wait": cmd.add_argument("--timeout", type=float, default=900); cmd.add_argument("--interval", type=float, default=2); cmd.add_argument("--output-dir"); cmd.add_argument("--no-download", action="store_true")
        if name == "download": cmd.add_argument("--output-dir")
    hist = sub.add_parser("history", help="Show local generation history"); hist.add_argument("--limit", type=int, default=20); hist.add_argument("--json", action="store_true")
    agent = sub.add_parser("agent", help="Plan or execute agentic media-production workflows")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_plan = agent_sub.add_parser("plan", help="Route a natural brief and emit a reproducible production plan")
    _add_agent_flags(agent_plan); agent_plan.add_argument("--save", help="Write a private plan manifest")
    agent_run = agent_sub.add_parser("run", help="Execute ready generation stages and stop at review gates")
    _add_agent_flags(agent_run)
    agent_run.add_argument("--manifest", help="Private run manifest path; an existing matching file is resumed")
    agent_run.add_argument("--selected-file", help="Reviewed campaign winner to animate when resuming an awaiting-review manifest")
    agent_run.add_argument(
        "--max-jobs", type=_positive_int,
        help="Maximum paid jobs; defaults to saved preferences (initially 5)",
    )
    doctor = sub.add_parser("doctor", help="Check local runtime without spending credits")
    doctor.add_argument("--json", action="store_true")
    catalog = sub.add_parser("catalog", help="Audit documented model/operation coverage")
    catalog.add_argument("action", choices=["audit"])
    catalog.add_argument("--kind")
    catalog.add_argument("--limit", type=_positive_int)
    catalog.add_argument("--refresh", action="store_true")
    catalog.add_argument("--json", action="store_true")
    chat = sub.add_parser("chat", help="Call a documented KIE language model (billable)")
    chat.add_argument("model")
    chat.add_argument("prompt", nargs="?")
    chat.add_argument("--input-file", help="JSON request object for multimodal inputs/tools")
    chat.add_argument("--param", action="append", default=[])
    chat.add_argument("--stream", action="store_true", help="Print JSONL stream events and a final result")
    chat.add_argument("--json", action="store_true")
    from .project_cli import add_parser
    add_parser(sub)
    return parser


def _model_rows(kind: str | None) -> list[dict[str, Any]]:
    return [{"id": m.id, "name": m.name, "kind": m.kind, "aliases": list(m.aliases), "description": m.description, "docs": m.docs} for m in list_models(kind)]


def _resolve_model(
    name: str,
    *,
    kind: str | None = None,
    refresh: bool = False,
    allow_passthrough: bool = False,
    needs_reference: bool | None = None,
) -> ModelSpec:
    model = get_model(name)
    if model.kind != "custom":
        if kind and model.kind != kind:
            raise ModelValidationError(f"Requested {kind} model, got {model.kind}: {model.id}")
        if refresh:
            return DocsCatalog().resolve(model.name, kind=kind or model.kind, refresh=True, needs_reference=needs_reference)
        return model
    try:
        return DocsCatalog().resolve(name, kind=kind, refresh=refresh, needs_reference=needs_reference)
    except CatalogError:
        technical_id = "/" in name and not any(char.isspace() for char in name)
        if allow_passthrough and technical_id:
            return model
        raise


def _model_detail(model: ModelSpec) -> dict[str, Any]:
    curated_ids = {item.id for item in list_models()}
    source = "curated" if model.id in curated_ids else ("passthrough" if model.kind == "custom" else "dynamic-docs")
    return {
        "id": model.id,
        "name": model.name,
        "kind": model.kind,
        "source": source,
        "aliases": list(model.aliases),
        "description": model.description,
        "docs": model.docs,
        "family": model.family,
        "endpoint": model.endpoint,
        "input_schema": model.input_schema,
        "support_status": "schema_validated" if model.kind != "custom" else "unvalidated_passthrough",
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
                "min_length": spec.min_length,
                "max_length": spec.max_length,
            }
            for key, spec in model.fields.items()
        },
    }


def _live_model_rows(query: str, kind: str | None, refresh: bool) -> list[dict[str, Any]]:
    return [entry.to_dict() for entry in DocsCatalog().search(query, kind=kind, refresh=refresh)]


def _cost_estimates(history: HistoryStore) -> dict[str, float]:
    return {
        model: float(values["median_credits"])
        for model, values in history.cost_profile().items()
    }


def _result_dict(result: TaskResult, paths: list[str] | None = None) -> dict[str, Any]:
    return {"task_id": result.task_id, "model": result.model, "state": result.state, "urls": result.urls, "files": paths or [], "output": result.output, "credits_consumed": result.credits_consumed, "fail_code": result.fail_code, "fail_message": result.fail_message}


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
    scalar_fields = {
        "image_url": "image", "first_frame_url": "image", "last_frame_url": "image",
        "video_url": "video", "audio_url": "audio",
    }
    list_fields = {
        "image_urls": "image", "reference_image_urls": "image",
        "video_urls": "video", "reference_video_urls": "video",
        "audio_urls": "audio", "reference_audio_urls": "audio",
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
    for key, value in values.items():
        if isinstance(value, dict):
            _resolve_media_params(client, value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _resolve_media_params(client, item)


def _apply_media(client: KieClient, model_id: str, values: dict[str, Any], args: argparse.Namespace, spec: ModelSpec | None = None) -> None:
    del client  # Upload/URL resolution deliberately happens only after validation.
    model = spec or get_model(model_id)
    fields = set(model.fields)
    requested = bool(args.image or args.start_image or args.end_image or args.reference_image or args.reference_video or args.reference_audio)
    if not requested:
        return
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

    def put(items: list[str], candidates: tuple[str, ...], label: str) -> None:
        if not items:
            return
        target = next((name for name in candidates if name in fields), None)
        if target is None and model.kind == "custom":
            target = candidates[0]
        if target is None:
            raise ModelValidationError(f"{model.id} does not accept {label} input flags")
        field_type = model.fields[target].type if target in model.fields else list
        if field_type is list:
            existing = values.get(target, [])
            if not isinstance(existing, list):
                raise ModelValidationError(f"Cannot combine media flags for {target}")
            values[target] = [*existing, *items]
        else:
            if len(items) != 1 or target in values:
                raise ModelValidationError(f"{target} accepts exactly one media input")
            values[target] = items[0]

    images = ([args.start_image] if args.start_image else []) + list(args.image)
    image_targets = ("first_frame_url", "image_urls", "image_url") if model.kind == "video" else ("image_urls", "image_url", "first_frame_url")
    put(images, image_targets, "image")
    put([args.end_image] if args.end_image else [], ("last_frame_url",), "end-image")
    put(list(args.reference_image), ("reference_image_urls", "image_urls", "image_url", "first_frame_url"), "reference-image")
    put(list(args.reference_video), ("reference_video_urls", "video_urls", "video_url"), "reference-video")
    put(list(args.reference_audio), ("reference_audio_urls", "audio_urls", "audio_url"), "reference-audio")


def _generate(client: KieClient, history: HistoryStore, args: argparse.Namespace, model_name: str, prompt: str, shortcut_values: dict[str, Any] | None = None, expected_kind: str | None = None) -> int:
    spec = _resolve_model(model_name, kind=expected_kind, allow_passthrough=True)
    if spec.family != "task":
        raise ModelValidationError("Use the chat command for synchronous/streaming language models")
    if expected_kind and spec.kind != expected_kind:
        raise ModelValidationError(f"The {expected_kind} shortcut requires model kind {expected_kind}, got {spec.kind}: {spec.id}")
    values = parse_key_values(args.param)
    media_param_fields = {
        "image_url", "image_urls", "first_frame_url", "last_frame_url", "reference_image_urls",
        "video_url", "video_urls", "reference_video_urls", "audio_url", "audio_urls", "reference_audio_urls",
    }
    has_media_flags = bool(args.image or args.start_image or args.end_image or args.reference_image or args.reference_video or args.reference_audio)
    if has_media_flags and set(values).intersection(media_param_fields):
        raise ModelValidationError("Do not mix media --param fields with dedicated media flags")
    shortcut_values = shortcut_values or {}
    if spec.kind != "custom":
        known_fields = set(spec.input_schema.get("properties", {})) if spec.input_schema else set(spec.fields)
        unknown_params = set(values) - known_fields
        if unknown_params:
            raise ModelValidationError(f"Unknown input parameter(s) for {spec.id}: {', '.join(sorted(unknown_params))}")
        unsupported_shortcuts = {key for key, value in shortcut_values.items() if value is not None and key not in spec.fields}
        if unsupported_shortcuts:
            raise ModelValidationError(f"Unsupported shortcut option(s) for {spec.id}: {', '.join(sorted(unsupported_shortcuts))}")
    if spec.kind == "custom":
        values.update({key: value for key, value in shortcut_values.items() if value is not None})
    else:
        values.update({key: value for key, value in shortcut_values.items() if key in spec.fields and value is not None})
    if prompt is not None:
        values["prompt"] = prompt
    _apply_media(client, spec.id, values, args, spec)
    if args.wait:
        validate_wait_options(args.wait_timeout, args.wait_interval)
    # Static validation before any upload or paid task creation.
    prepare_model_input(spec, values)
    _resolve_media_params(client, values)
    input_data = prepare_model_input(spec, values)
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
        item["model"] = item.get("model") or spec.id
        _safe_history_append(history, item)
    except Exception as exc:
        _safe_history_append(history, {"task_id": task_id, "model": spec.id, "state": "error", "error": str(exc)})
        if isinstance(exc, KieApiError):
            raise KieApiError(f"Task {task_id}: {exc}", exc.code, exc.payload) from exc
        raise KieApiError(f"Task {task_id}: {exc}") from exc
    _print(item, args.json)
    return 0


def _update_preferences(args: argparse.Namespace, store: PreferencesStore) -> Preferences:
    current = store.load()
    if args.clear_image_model and args.image_model:
        raise PreferencesError("Use either --image-model or --clear-image-model")
    if args.clear_video_model and args.video_model:
        raise PreferencesError("Use either --video-model or --clear-video-model")
    image_model = current.image_model
    video_model = current.video_model
    if args.clear_image_model:
        image_model = None
    elif args.image_model:
        image_model = _resolve_model(args.image_model, kind="image", allow_passthrough=True).id
    if args.clear_video_model:
        video_model = None
    elif args.video_model:
        video_model = _resolve_model(args.video_model, kind="video", allow_passthrough=True).id
    excluded = [] if args.clear_exclusions else list(current.excluded_models)
    for name in args.exclude_model:
        model_id = _resolve_model(name, allow_passthrough=True).id
        if model_id not in excluded:
            excluded.append(model_id)
    updated = Preferences(
        default_tier=args.tier or current.default_tier,
        image_model=image_model,
        video_model=video_model,
        excluded_models=tuple(excluded),
        max_jobs=args.max_jobs or current.max_jobs,
    ).validate()
    store.save(updated)
    return updated


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = build_parser(); args = parser.parse_args(argv)
    try:
        if args.command == "project":
            from .project_cli import dispatch
            result = dispatch(args)
            _print(result, args.json)
            return 1 if result.get("state") in {"needs_recovery", "needs_changes", "asset_changed"} else 0
        if args.command == "doctor":
            from .inspection import doctor
            _print(doctor(), args.json)
            return 0
        if args.command == "catalog":
            from .inspection import audit_catalog
            _print(audit_catalog(DocsCatalog(), kind=args.kind, limit=args.limit, refresh=args.refresh), args.json)
            return 0
        if args.command == "chat":
            from .language import complete
            spec = _resolve_model(args.model)
            values = json.loads(Path(args.input_file).read_text(encoding="utf-8")) if args.input_file else {}
            if not isinstance(values, dict):
                raise ValueError("Language input file must contain a JSON object")
            values.update(parse_key_values(args.param))
            if args.prompt:
                target = "input" if spec.family == "responses" else ("contents" if spec.family == "gemini" else "messages")
                if target in values:
                    raise ValueError(f"Use either prompt or explicit {target}, not both")
                if target == "input":
                    values[target] = args.prompt
                elif target == "contents":
                    values[target] = [{"role": "user", "parts": [{"text": args.prompt}]}]
                else:
                    values[target] = [{"role": "user", "content": args.prompt}]
            if "stream" in spec.fields:
                values["stream"] = args.stream
            # Complete static validation before reading credentials/submitting.
            prepare_model_input(spec, values)
            client = KieClient(_load_env_key(args.env_file) or "")
            result = complete(client, spec, values,
                on_event=(lambda event: print(json.dumps({"event": event}, ensure_ascii=False))) if args.stream else None)
            _safe_history_append(HistoryStore(), {"model": spec.id, "family": spec.family,
                "state": "completed", "response_id": result.get("id"), "usage": result.get("usage"),
                "credits_consumed": result.get("credits_consumed")})
            if args.stream:
                print(json.dumps({"result": result}, ensure_ascii=False))
            else:
                _print(result, args.json)
            return 0
        if args.command == "models":
            rows = _live_model_rows(args.search, args.kind, args.refresh) if (args.live or args.search or args.refresh) else _model_rows(args.kind)
            _print(rows, args.json)
            return 0
        if args.command == "model":
            _print(_model_detail(_resolve_model(args.name, kind=args.kind, refresh=args.refresh)), args.json)
            return 0
        if args.command == "preferences":
            store = PreferencesStore()
            if args.preferences_command == "show":
                payload = store.load().to_dict()
                payload["observed_costs"] = HistoryStore().cost_profile()
            elif args.preferences_command == "set":
                payload = _update_preferences(args, store).to_dict()
            else:
                payload = store.reset().to_dict()
            _print(payload, args.json)
            return 0
        if args.command == "agent":
            preferences = Preferences() if args.no_preferences else PreferencesStore().load()
            if args.budget:
                selected_tier = "budget" if args.budget == "fast" else "balanced"
            else:
                selected_tier = args.tier or preferences.default_tier
            requested_image = args.image_model or preferences.image_model
            requested_video = args.video_model or preferences.video_model
            resolved_image = _resolve_model(
                requested_image, kind="image", allow_passthrough=True, needs_reference=bool(args.media)
            ).id if requested_image else None
            video_needs_reference = bool(args.media) or args.workflow in {"image-to-video", "campaign"}
            resolved_video = _resolve_model(
                requested_video, kind="video", allow_passthrough=True, needs_reference=video_needs_reference
            ).id if requested_video else None
            history = HistoryStore()
            plan = build_plan(
                args.brief, workflow=args.workflow, media=args.media,
                reference_videos=args.reference_video, reference_audio=args.reference_audio, count=args.count,
                aspect_ratio=args.aspect_ratio, duration=args.duration, budget=args.budget or "quality",
                tier=selected_tier, image_model=resolved_image, video_model=resolved_video,
                excluded_models=list(preferences.excluded_models), cost_estimates=_cost_estimates(history),
                output_dir=args.output_dir, mode=args.mode, scope=args.scope,
            )
            if args.agent_command == "plan":
                if args.save:
                    save_manifest(args.save, plan, {"state": "planned", "results": []})
                _print(plan.to_dict(), args.json)
                return 0
            max_jobs = args.max_jobs or preferences.max_jobs
            if plan.estimated_jobs > max_jobs:
                raise PlanError(
                    f"Plan declares {plan.estimated_jobs} jobs, above --max-jobs {max_jobs}; "
                    "inspect the free plan and raise --max-jobs explicitly to authorize the larger bundle"
                )
            if args.env_file:
                os.environ["KIE_MEDIA_ENV_FILE"] = str(Path(args.env_file).expanduser())
            manifest = Path(args.manifest).expanduser().resolve(strict=False) if args.manifest else new_manifest_path(plan)
            with production_lock(plan), manifest_lock(manifest):
                prior_execution = None
                if manifest.exists():
                    stored = load_manifest(manifest)
                    if stored.get("plan_fingerprint") != plan_fingerprint(plan):
                        raise PlanError("Existing manifest does not match this production plan")
                    prior_execution = stored["execution"]
                else:
                    save_manifest(manifest, plan, {"state": "planned", "running_stage": None, "results": []})
                execution = execute_plan(
                    plan,
                    prior_execution=prior_execution,
                    selected_file=args.selected_file,
                    checkpoint=lambda state: save_manifest(manifest, plan, state),
                )
            _print({"workflow": plan.workflow, "manifest": str(manifest), **execution}, args.json)
            return 1 if execution.get("state") in {"failed", "checkpoint_failed", "needs_recovery"} else 0
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
            try:
                item = _result_dict(parse_result(client.get_task(args.task_id)))
                _safe_history_append(history, item)
                _print(item, args.json)
                return 0
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
    except (KieApiError, ModelValidationError, PlanError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Source-video transformations with content receipts and paid-task recovery."""
from __future__ import annotations

import copy
import hashlib
import html
import json
import math
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from .agent import manifest_lock
from .client import SUCCESS_STATES, _media_signature_valid
from .media import probe
from .models import prepare_model_input
from .storage import atomic_json


def _now():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path, kind):
    path = Path(path).expanduser().resolve()
    mime = mimetypes.guess_type(path.name)[0] or ""
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f"Missing or empty {kind}: {path}")
    if not mime.startswith(kind + "/") or not _media_signature_valid(path, mime):
        raise ValueError(f"Invalid {kind} file: {path}")
    return {"path": str(path), "sha256": _file_hash(path), "bytes": path.stat().st_size,
            "mime": mime}


def _fingerprint(plan):
    return _digest({k: v for k, v in plan.items() if k != "fingerprint"})


def build_recast_plan(video: Path, prompt: str, *, references=None, mode="motion-transfer",
                      duration=None, resolution="720p", keep_original_sound=False, take=1):
    """Plan offline. Files stay local until an explicit run; FFprobe is required."""
    from .recast_models import recast_capabilities, prepare_recast_request
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Describe what to change and what should stay in the source video")
    if isinstance(take, bool) or not isinstance(take, int) or take < 1:
        raise ValueError("take must be a positive integer")
    if not isinstance(keep_original_sound, bool):
        raise ValueError("keep_original_sound must be boolean")
    caps = recast_capabilities(mode)
    refs = list(references or [])
    if not caps["min_reference_images"] <= len(refs) <= caps["max_reference_images"]:
        raise ValueError(f"{mode} requires {caps['min_reference_images']}–{caps['max_reference_images']} reference images")
    if resolution not in caps["resolutions"]:
        raise ValueError(f"{mode} supports resolutions: {', '.join(caps['resolutions'])}")
    source = _record(video, "video")
    images = [_record(path, "image") for path in refs]
    metadata = probe(Path(source["path"]))
    seconds = metadata.get("duration", 0)
    if not metadata.get("video") or isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds):
        raise ValueError("Source must be a readable video with finite duration")
    if seconds <= 0:
        raise ValueError("Source must have a positive duration")
    lower, upper = caps.get("source_min_seconds"), caps.get("source_max_seconds")
    if (lower is not None and seconds < lower) or (upper is not None and seconds > upper):
        raise ValueError(f"{mode} source duration must be {caps['source_min_seconds']}–{caps['source_max_seconds']} seconds")
    source_caps = caps.get("source_media") or {}
    image_caps = caps.get("reference_media") or {}
    if source["bytes"] > (source_caps.get("max_bytes") or 1_000_000_000):
        raise ValueError("Source exceeds this model's video size limit")
    for image in images:
        if image["bytes"] > (image_caps.get("max_bytes") or 1_000_000_000):
            raise ValueError("Reference exceeds this model's image size limit")
        _check_format(image, image_caps)
        info = probe(Path(image["path"]))
        if not info.get("image"):
            raise ValueError("Reference must be a still image")
        _check_dimensions(info, image_caps, "image")
        if image_caps.get("allow_alpha") is False and info.get("has_alpha"):
            raise ValueError("This model requires a reference image without an alpha channel")
    _check_dimensions(metadata, source_caps, "video")
    _check_format(source, source_caps)
    if duration is None:
        duration = math.ceil(seconds)
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 1:
        raise ValueError("duration must be a positive integer")
    if caps.get("output_duration") == "source_determined" and duration != math.ceil(seconds):
        raise ValueError("This model derives duration from the source; trim the source before planning")
    spec, values = prepare_recast_request(mode, prompt.strip(), video=source["path"],
        references=[item["path"] for item in images], duration=duration,
        resolution=resolution, keep_original_sound=keep_original_sound)
    # The adapter supplies documented fields only; no upload occurs in planning.
    values = prepare_model_input(spec, values)
    plan = {"version": 1, "workflow": "recast", "status": "ready", "mode": mode,
            "model": spec.id, "docs": spec.docs, "prompt": prompt.strip(),
            "source": source, "references": images, "source_metadata": metadata,
            "duration": duration, "resolution": resolution,
            "keep_original_sound": keep_original_sound, "take": take,
            "input": values, "estimated_jobs": 1, "estimated_credits": None,
            "credit_estimate_basis": "unavailable", "capabilities": caps,
            "quality_evidence": "documented_contract_and_offline_tests; no_paid_generation_test",
            "visual_review": "required_after_generation"}
    plan["fingerprint"] = _fingerprint(plan)
    return plan


def _check_dimensions(info, caps, kind):
    width, height = info.get("width"), info.get("height")
    if not width or not height:
        raise ValueError(f"Cannot read {kind} dimensions")
    minimum, maximum = caps.get("min_dimension_px") or 0, caps.get("max_dimension_px") or math.inf
    if min(width, height) < minimum or max(width, height) > maximum:
        raise ValueError(f"{kind} dimensions are outside this model's supported range")
    ratio = width / height
    if not caps.get("min_ratio", 0) <= ratio <= caps.get("max_ratio", math.inf):
        raise ValueError(f"{kind} aspect ratio is outside this model's supported range")
    if width * height > caps.get("max_pixels", math.inf):
        raise ValueError(f"{kind} exceeds this model's pixel limit")
    if "min_fps" in caps or "max_fps" in caps:
        fps = info.get("fps", 0)
        if not isinstance(fps, (int, float)) or not math.isfinite(fps) or not caps.get("min_fps", 0) <= fps <= caps.get("max_fps", math.inf):
            raise ValueError(f"{kind} frame rate is outside this model's supported range")


def _check_format(record, caps):
    formats = caps.get("formats")
    if not formats or "provider_documentation_not_specific" in formats:
        return
    name = Path(record["path"]).suffix.lower().lstrip(".")
    normalized = {"quicktime": "mov", "jpeg": "jpg"}
    if normalized.get(name, name) not in {normalized.get(item, item) for item in formats}:
        raise ValueError("Media format is unsupported by this model")


def _validate_plan(plan, *, verify_files=False):
    from .recast_models import prepare_recast_request
    if not isinstance(plan, dict) or plan.get("version") != 1 or plan.get("workflow") != "recast":
        raise ValueError("Invalid recast plan")
    required = {"mode", "prompt", "source", "references", "duration", "resolution", "keep_original_sound", "model", "input", "fingerprint", "take"}
    if not required.issubset(plan) or not isinstance(plan["source"], dict) or not isinstance(plan["references"], list):
        raise ValueError("Invalid recast plan")
    for record in [plan["source"], *plan["references"]]:
        if not isinstance(record, dict) or not all(isinstance(record.get(key), str) and record[key] for key in ("path", "sha256")) or not isinstance(record.get("bytes"), int):
            raise ValueError("Invalid recast plan media record")
    if plan.get("fingerprint") != _fingerprint(plan):
        raise ValueError("Recast plan changed; create a fresh plan")
    spec, values = prepare_recast_request(plan["mode"], plan["prompt"],
        video=plan["source"]["path"], references=[item["path"] for item in plan["references"]],
        duration=plan["duration"], resolution=plan["resolution"],
        keep_original_sound=plan["keep_original_sound"])
    values = prepare_model_input(spec, values)
    if spec.id != plan["model"] or values != plan["input"]:
        raise ValueError("Model contract changed; create a fresh recast plan")
    if verify_files:
        for item in [plan["source"], *plan["references"]]:
            path = Path(item["path"])
            if not path.is_file() or path.stat().st_size != item["bytes"] or _file_hash(path) != item["sha256"]:
                raise ValueError(f"Input changed after planning: {path}")
    return spec


def load_recast_manifest(manifest):
    value = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("execution"), dict):
        raise ValueError("Invalid recast manifest")
    _validate_plan(value.get("plan"))
    states = {"planned", "submitting", "submitted", "pending", "needs_recovery", "failed", "awaiting_review", "completed", "rejected"}
    execution = value["execution"]
    if execution.get("state") not in states or ("task_id" in execution and not isinstance(execution["task_id"], str)):
        raise ValueError("Invalid recast manifest execution state")
    return value


def _artifacts_valid(execution):
    artifacts = execution.get("artifacts", [])
    return bool(artifacts) and all(Path(item["path"]).is_file() and
        _file_hash(item["path"]) == item["sha256"] for item in artifacts)


def _resolve_inputs(client, values):
    values = copy.deepcopy(values)
    for key in ("video_url",):
        if key in values:
            values[key] = client.resolve_media(values[key], "video")
    for key in ("reference_image", "image_url"):
        if key in values:
            values[key] = client.resolve_media(values[key], "image")
    for key, kind in (("video_urls", "video"), ("input_urls", "image"), ("image_urls", "image")):
        if key in values:
            values[key] = [client.resolve_media(item, kind) for item in values[key]]
    return values


def run_recast(plan, manifest: Path, *, max_jobs=1, client=None):
    """Run one paid operation, or resume its recorded task and downloads."""
    if isinstance(max_jobs, bool) or not isinstance(max_jobs, int) or max_jobs < 1:
        raise ValueError("max_jobs must authorize at least one job")
    spec = _validate_plan(plan, verify_files=True)
    manifest = Path(manifest).expanduser().resolve()
    owner_path = manifest.parent / ".kie-media-locks" / ("recast-" + plan["fingerprint"] + ".json")
    with manifest_lock(owner_path), manifest_lock(manifest):
        # Alternate manifest names in this output directory cannot duplicate a take.
        if owner_path.exists():
            owner = json.loads(owner_path.read_text(encoding="utf-8"))
            if owner.get("manifest") != str(manifest):
                raise ValueError(f"This take belongs to {owner.get('manifest')}; resume that manifest or plan a new --take")
            if not manifest.exists():
                raise ValueError("Recast manifest missing; restore it before attempting paid work")
        if manifest.exists():
            stored = load_recast_manifest(manifest)
            if stored["plan"]["fingerprint"] != plan["fingerprint"]:
                raise ValueError("Existing manifest belongs to a different recast plan")
        else:
            stored = {"version": 1, "plan": copy.deepcopy(plan),
                      "execution": {"state": "planned", "created_at": _now()}}
            atomic_json(manifest, stored)
        if not owner_path.exists():
            atomic_json(owner_path, {"manifest": str(manifest), "fingerprint": plan["fingerprint"]})
        execution = stored["execution"]

        def persist():
            atomic_json(manifest, stored)

        def result():
            return {"manifest": str(manifest), "model": plan["model"], **copy.deepcopy(execution)}

        if execution["state"] in {"awaiting_review", "completed", "rejected"}:
            if not _artifacts_valid(execution):
                return {**result(), "state": "asset_changed"}
            return result()
        if execution["state"] in {"needs_recovery", "submitting", "submitted", "pending"} and not execution.get("task_id"):
            return {**result(), "state": "needs_recovery"}
        if execution["state"] == "failed":
            return result()
        if client is None:
            raise ValueError("A KIE client is required for production")
        if not execution.get("task_id"):
            values = _resolve_inputs(client, plan["input"])
            values = prepare_model_input(spec, values)
            execution.update(state="submitting", validated_request={"model": spec.id, "input": values,
                "docs": spec.docs, "schema_sha256": _digest(spec.input_schema)})
            persist()  # If this write fails, task creation must not happen.
            try:
                task_id, _ = client.create_task(spec.id, values)
                if not isinstance(task_id, str) or not task_id.strip():
                    raise ValueError("Provider returned no task ID")
                execution.update(task_id=task_id, state="submitted")
                persist()  # Preserve task ID before polling or downloading.
            except Exception as exc:
                execution.update(state="submitted" if execution.get("task_id") else "needs_recovery", error=str(exc))
                persist()
                return result()
        task_id = execution["task_id"]
        try:
            completed = client.wait(task_id)
            if completed.state not in SUCCESS_STATES:
                execution.update(state="failed", error=completed.fail_message or "Provider task failed")
            else:
                paths = client.download_urls(completed.urls, manifest.parent / "assets", task_id=task_id)
                artifacts = [_record(path, "video") for path in paths]
                if not artifacts:
                    raise ValueError("Generation returned no persistent video")
                for artifact in artifacts:
                    if not probe(Path(artifact["path"])).get("video"):
                        raise ValueError("Output is not a readable video")
                execution.update(state="awaiting_review", artifacts=artifacts,
                    credits_consumed=completed.credits_consumed, completed_at=_now(),
                    visual_review="not_performed")
                execution.pop("error", None)
            persist()
        except Exception as exc:
            execution.update(state="pending", error=str(exc))
            persist()
        return result()


def recover_recast(manifest: Path, task_id: str):
    """Attach an explicitly inspected provider task after an ambiguous create."""
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("A known provider task ID is required")
    manifest = Path(manifest).expanduser().resolve()
    with manifest_lock(manifest):
        stored = load_recast_manifest(manifest)
        execution = stored["execution"]
        if execution.get("task_id") or execution["state"] not in {"submitting", "submitted", "pending", "needs_recovery"}:
            raise ValueError("Recovery requires an unresolved creation without a task ID")
        execution.update(task_id=task_id.strip(), state="submitted", recovered_at=_now())
        atomic_json(manifest, stored)
        return {"manifest": str(manifest), **execution}


def review_recast(manifest: Path, decision: str, note: str):
    if decision not in {"accepted", "rejected"} or not isinstance(note, str) or not note.strip():
        raise ValueError("Review needs an accepted/rejected decision and a meaningful note")
    manifest = Path(manifest).expanduser().resolve()
    with manifest_lock(manifest):
        stored = load_recast_manifest(manifest)
        execution = stored["execution"]
        if execution["state"] not in {"awaiting_review", "completed", "rejected"} or not _artifacts_valid(execution):
            raise ValueError("Review requires unchanged downloaded output")
        execution.update(state="completed" if decision == "accepted" else "rejected",
                         visual_review={"decision": decision, "note": note.strip(), "at": _now()})
        atomic_json(manifest, stored)
        return {"manifest": str(manifest), **execution}


def compare_recast(manifest: Path):
    """Write a local side-by-side viewer for the source and this take."""
    manifest = Path(manifest).expanduser().resolve()
    with manifest_lock(manifest):
        stored = load_recast_manifest(manifest)
        plan, execution = stored["plan"], stored["execution"]
        _validate_plan(plan, verify_files=True)
        if not _artifacts_valid(execution):
            raise ValueError("Comparison needs unchanged downloaded output")
        target = manifest.with_suffix(".html")
        def player(label, path):
            return '<section><h2>' + label + '</h2><video controls preload="metadata" src="' + html.escape(Path(path).as_uri(), quote=True) + '"></video></section>'
        body = player("Source", plan["source"]["path"])
        body += "".join(player("Take " + str(plan["take"]), item["path"]) for item in execution["artifacts"])
        target.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Recast review</title>'
            '<style>body{background:#111827;color:#f3f4f6;font:17px system-ui;margin:32px}main{display:flex;gap:24px;flex-wrap:wrap}section{flex:1;min-width:280px}video{width:100%;max-height:70vh}p{max-width:90ch}</style>'
            '<h1>Recast review</h1><p>' + html.escape(plan["prompt"]) + '</p><p>' + html.escape(plan["mode"] + ' · ' + plan["model"]) + '</p><main>' + body + '</main>'
            '<p>Check identity, hands, camera, timing, unaffected details and sound. Record the review with kie-media recast review.</p></html>', encoding="utf-8")
        return {"file": str(target), "state": execution["state"]}

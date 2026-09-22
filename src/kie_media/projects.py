"""Editable scene projects with immutable receipts and selective invalidation."""
from __future__ import annotations

import copy
import hashlib
import html
import json
import math
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .agent import manifest_lock
from .catalog import DocsCatalog
from .client import KieClient, SUCCESS_STATES
from .models import get_model, prepare_model_input
from .storage import atomic_json


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def file_hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> dict:
    project = json.loads(path.read_text(encoding="utf-8"))
    _validate(project)
    return project


def _validate(project: dict) -> None:
    if not isinstance(project, dict) or project.get("version") != 1:
        raise ValueError("Unsupported project format")
    shots = project.get("shots", [])
    if not isinstance(shots, list) or not 1 <= len(shots) <= 50:
        raise ValueError("Project must contain 1–50 shots")
    ids = set()
    for shot in shots:
        if not isinstance(shot, dict) or not isinstance(shot.get("id"), str) or shot["id"] in ids:
            raise ValueError("Shot IDs must be unique strings")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", shot["id"]):
            raise ValueError("Shot IDs may contain letters, numbers, hyphens and underscores")
        ids.add(shot["id"])
        duration = shot.get("duration")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 1 <= duration <= 600:
            raise ValueError("Shot duration must be a finite number from 1 to 600")
        if any(not isinstance(shot.get(key), str) for key in ("prompt", "motion", "narration")):
            raise ValueError("Shot prompt, motion and narration must be text")
        if not shot["prompt"].strip() or not shot["motion"].strip():
            raise ValueError("Each shot needs a visual prompt and motion direction")
        if not isinstance(shot.get("entities"), list) or any(not isinstance(e, str) for e in shot["entities"]):
            raise ValueError("Shot entities must be a list of library names")
        take = shot.get("take", 1)
        if isinstance(take, bool) or not isinstance(take, int) or take < 1:
            raise ValueError("Shot take must be a positive integer")
    if project.get("aspect_ratio") not in {"16:9", "9:16", "1:1", "4:5"}:
        raise ValueError("Supported project ratios: 16:9, 9:16, 1:1, 4:5")
    if not isinstance(project.get("jobs"), list) or not isinstance(project.get("entities"), dict):
        raise ValueError("Invalid project ledger/library")
    if not isinstance(project.get("models"), dict) or any(not isinstance(project["models"].get(k), str) or not project["models"][k] for k in ("image", "video", "voice", "music")):
        raise ValueError("Project needs image/video/voice/music model settings")
    if any(not isinstance(j, dict) or not {"id", "stage_id", "fingerprint", "state"}.issubset(j) for j in project["jobs"]):
        raise ValueError("Invalid job receipt")


def create_project(path: Path, brief: str, *, shots=3, aspect_ratio="16:9",
                   image_model="image-fast", video_model="video-kling-image") -> dict:
    path = path.expanduser().resolve()
    if not brief.strip() or isinstance(shots, bool) or not 1 <= shots <= 50:
        raise ValueError("A brief and 1–50 shots are required")
    views = ["Wide establishing view", "Close detail view", "Hero closing view"]
    project = {"version": 1, "id": uuid.uuid4().hex, "revision": 1, "created_at": _now(),
        "brief": brief, "aspect_ratio": aspect_ratio, "entities": {}, "jobs": [], "changes": [],
        "models": {"image": image_model, "video": video_model,
                   "voice": "elevenlabs/text-to-speech-multilingual-v2", "music": "ai-music-api/generate"},
        "voice": None, "music_prompt": "", "shots": [
            {"id": f"scene-{i + 1}", "prompt": f"{brief}. {views[i % len(views)]}. Consistent subject, materials and palette.",
             "motion": "Slow controlled camera push-in; preserve subject identity and geometry.",
             "narration": "", "duration": 5, "entities": [], "take": 1}
            for i in range(shots)]}
    _validate(project)
    with manifest_lock(path):
        if path.exists():
            raise ValueError("Project already exists; edit or resume it")
        atomic_json(path, project)
    return project


def _stages(project: dict) -> list[dict]:
    stages = []
    for shot in project["shots"]:
        entities = shot.get("entities", [])
        refs = []
        for name in entities:
            if name not in project["entities"]:
                raise ValueError(f"Unknown entity: {name}")
            refs.append(project["entities"][name])
        image = {"id": shot["id"] + ".image", "kind": "image", "model": project["models"]["image"],
                 "prompt": shot["prompt"], "references": refs, "aspect_ratio": project["aspect_ratio"], "take": shot.get("take", 1)}
        image["fingerprint"] = digest(image)
        stages.append(image)
        video = {"id": shot["id"] + ".video", "kind": "video", "model": project["models"]["video"],
                 "prompt": shot["motion"], "duration": shot["duration"], "aspect_ratio": project["aspect_ratio"],
                 "depends_on": image["id"], "dependency_fingerprint": image["fingerprint"]}
        video["fingerprint"] = digest(video)
        stages.append(video)
        if shot.get("narration", "").strip():
            voice = {"id": shot["id"] + ".voice", "kind": "voice", "model": project["models"]["voice"],
                     "text": shot["narration"], "voice": project.get("voice")}
            voice["fingerprint"] = digest(voice)
            stages.append(voice)
    if project.get("music_prompt", "").strip():
        music = {"id": "music", "kind": "music", "model": project["models"]["music"],
                 "style": project["music_prompt"], "duration": max(10, sum(s["duration"] for s in project["shots"]))}
        music["fingerprint"] = digest(music)
        stages.append(music)
    return stages


def _receipt(project: dict, stage: dict) -> dict | None:
    return next((j for j in reversed(project["jobs"]) if j["stage_id"] == stage["id"] and j["fingerprint"] == stage["fingerprint"]), None)


def _asset_valid(root: Path, job: dict) -> bool:
    files = job.get("artifacts", [])
    return bool(files) and all((root / a["path"]).is_file() and file_hash(root / a["path"]) == a["sha256"] for a in files)


def project_plan(path: Path) -> dict:
    path = path.expanduser().resolve()
    project = _read(path)
    return _plan(project, path.parent)


def _plan(project: dict, root: Path) -> dict:
    rows = []
    for stage in _stages(project):
        job = _receipt(project, stage)
        state = job["state"] if job else "pending"
        if state == "pending" and _image_not_required(project, stage, root):
            state = "not_required_imported_video"
        if state == "success" and not _asset_valid(root, job):
            state = "asset_changed"
        rows.append({**stage, "state": state, "review": (job or {}).get("review"), "task_id": (job or {}).get("task_id")})
    return {"project_id": project["id"], "revision": project["revision"], "stages": rows,
            "pending_jobs": sum(r["state"] == "pending" for r in rows),
            "estimated_credits": None, "cost_note": "Job limit is enforced; credit prices are not guaranteed.",
            "assembly": "local renderer; reruns after changed video, narration or music"}


def _image_not_required(project: dict, stage: dict, root: Path) -> bool:
    if stage["kind"] != "image":
        return False
    video = next((s for s in _stages(project) if s.get("depends_on") == stage["id"]), None)
    receipt = _receipt(project, video) if video else None
    return bool(receipt and receipt.get("origin") == "imported" and receipt.get("state") == "success" and _asset_valid(root, receipt))


def revise_shot(path: Path, shot_id: str, changes: dict, *, dry_run=False) -> dict:
    path = path.expanduser().resolve()
    allowed = {"prompt", "motion", "narration", "duration", "entities", "take"}
    if not changes or set(changes) - allowed:
        raise ValueError("Only visual prompt, motion, narration, duration, entities and take can be edited")
    with manifest_lock(path):
        project = _read(path)
        before = {s["id"]: s["fingerprint"] for s in _stages(project)}
        shot = next((s for s in project["shots"] if s["id"] == shot_id), None)
        if shot is None:
            raise ValueError(f"Unknown shot: {shot_id}")
        shot.update(changes)
        _validate(project)
        after = {s["id"]: s["fingerprint"] for s in _stages(project)}
        affected = [key for key in dict.fromkeys([*before, *after]) if before.get(key) != after.get(key)]
        result = {"shot": shot_id, "affected_stages": affected + (["assembly"] if affected else []),
                  "new_jobs": sum(key in after for key in affected), "dry_run": dry_run}
        if not dry_run and affected:
            project["revision"] += 1
            project["changes"].append({"at": _now(), "revision": project["revision"], **result, "changes": changes})
            atomic_json(path, project)
        return result


def add_entity(path: Path, name: str, source: Path, description="") -> dict:
    path = path.expanduser().resolve()
    source = source.expanduser().resolve()
    if not name.strip() or not source.is_file() or source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Entity requires a name and a local PNG/JPEG/WebP reference")
    from .client import _media_signature_valid
    import mimetypes
    if not _media_signature_valid(source, mimetypes.guess_type(source)[0] or ""):
        raise ValueError("Entity reference is not a valid image")
    checksum = file_hash(source)
    with manifest_lock(path):
        project = _read(path)
        target = path.parent / "assets" / (checksum + source.suffix.lower())
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
        entity = {"name": name, "description": description, "path": target.relative_to(path.parent).as_posix(), "sha256": checksum}
        project["entities"][name] = entity
        project["revision"] += 1
        atomic_json(path, project)
    return entity


def configure_project(path: Path, *, music_prompt=None, voice=None, models=None) -> dict:
    path = path.expanduser().resolve()
    with manifest_lock(path):
        project = _read(path)
        if music_prompt is not None:
            project["music_prompt"] = music_prompt
        if voice is not None:
            project["voice"] = voice or None
        for kind, model in (models or {}).items():
            if kind not in {"image", "video", "voice", "music"} or not model.strip():
                raise ValueError("Invalid project model setting")
            project["models"][kind] = model
        project["revision"] += 1
        atomic_json(path, project)
    return {"models": project["models"], "voice": project["voice"], "music_prompt": project["music_prompt"]}


def _prepare(stage: dict, project: dict, root: Path, *, placeholder=False):
    spec = get_model(stage["model"])
    if spec.kind == "custom":
        spec = DocsCatalog().resolve(stage["model"])
    if spec.family != "task":
        raise ValueError("Scene generation requires an asynchronous media operation")
    values = {}
    kind = stage["kind"]
    if kind in {"image", "video"}:
        values["prompt"] = stage["prompt"]
        for field in ("aspect_ratio", "duration"):
            if field in spec.fields and field in stage:
                value = stage[field]
                values[field] = str(value) if spec.fields[field].type is str else value
        refs = []
        if kind == "image":
            for ref in stage["references"]:
                file = root / ref["path"]
                if not file.is_file() or file_hash(file) != ref["sha256"]:
                    raise ValueError(f"Entity reference changed: {ref['name']}")
                refs.append(str(file))
            if stage["references"]:
                values["prompt"] += " Preserve: " + "; ".join(r["description"] or r["name"] for r in stage["references"])
        else:
            image_stage = next(s for s in _stages(project) if s["id"] == stage["depends_on"])
            receipt = _receipt(project, image_stage)
            if placeholder:
                refs = ["https://example.invalid/approved-frame.png"]
            elif receipt and receipt.get("state") == "success" and _asset_valid(root, receipt):
                refs = [str(root / receipt["artifacts"][0]["path"])]
            else:
                raise ValueError("Video needs its accepted generated image")
        if refs:
            field = next((f for f in ("first_frame_url", "image_urls", "image_url", "reference_image_urls") if f in spec.fields), None)
            if not field:
                raise ValueError(f"{spec.id} cannot receive the required identity reference")
            if spec.fields[field].type is not list and len(refs) != 1:
                raise ValueError(f"{spec.id} accepts only one reference via {field}")
            values[field] = refs if spec.fields[field].type is list else refs[0]
    elif kind == "voice":
        values = {"text": stage["text"]}
        if stage.get("voice"):
            values["voice"] = stage["voice"]
    elif kind == "music":
        values = {"custom_mode": True, "instrumental": True, "model": "V6", "style": stage["style"],
                  "title": "Project soundtrack", "duration": stage["duration"]}
    return spec, prepare_model_input(spec, values)


def _production_runner(client: KieClient, project: dict, root: Path):
    def run(stage: dict, checkpoint: Callable) -> dict:
        from .cli import _resolve_media_params
        if stage.get("task_id"):
            task_id = stage["task_id"]
        else:
            spec, values = _prepare(stage, project, root)
            _resolve_media_params(client, values)
            values = prepare_model_input(spec, values)
            checkpoint(None, {"model": spec.id, "input": values,
                              "schema_sha256": digest(spec.input_schema), "docs": spec.docs})
            task_id, _ = client.create_task(spec.id, values)
            checkpoint(task_id)
        result = client.wait(task_id)
        if result.state not in SUCCESS_STATES:
            return {"state": "failed", "task_id": task_id, "error": result.fail_message}
        paths = client.download_urls(result.urls, root / "assets", task_id=task_id)
        return {"state": "success", "task_id": task_id, "files": paths, "credits_consumed": result.credits_consumed}
    return run


def run_project(path: Path, *, phase="images", max_jobs=5, runner=None, client=None) -> dict:
    path = path.expanduser().resolve()
    kinds = {"images": {"image"}, "videos": {"video"}, "audio": {"voice", "music"},
             "all": {"image", "video", "voice", "music"}}
    if phase not in kinds or isinstance(max_jobs, bool) or not isinstance(max_jobs, int) or max_jobs < 1:
        raise ValueError("Invalid phase or job limit")
    with manifest_lock(path):
        project = _read(path)
        order = {"image": 0, "video": 1, "voice": 2, "music": 3}
        stages = sorted([s for s in _stages(project) if s["kind"] in kinds[phase] and not _image_not_required(project, s, path.parent)], key=lambda s: order[s["kind"]])
        unresolved = [j for j in project["jobs"] if j["state"] in {"submitting", "needs_recovery"}]
        if unresolved:
            return {"state": "needs_recovery", "jobs": [j["id"] for j in unresolved]}
        needed = [s for s in stages if _receipt(project, s) is None]
        if len(needed) > max_jobs:
            raise ValueError(f"Phase needs {len(needed)} new jobs, above --max-jobs {max_jobs}")
        if runner is None:
            # Validate every requested stage before any upload or paid create.
            for stage in stages:
                if not _receipt(project, stage):
                    _prepare(stage, project, path.parent, placeholder=True)
            if client is None:
                raise ValueError("A KIE client is required for real production")
            runner = _production_runner(client, project, path.parent)
        for stage in stages:
            receipt = _receipt(project, stage)
            if receipt and receipt["state"] == "success":
                if not _asset_valid(path.parent, receipt):
                    return {"state": "asset_changed", "stage": stage["id"], "job_id": receipt["id"]}
                continue
            if receipt and receipt["state"] == "failed":
                return {"state": "needs_changes", "stage": stage["id"], "error": receipt.get("error")}
            if stage.get("depends_on"):
                dep = next(s for s in _stages(project) if s["id"] == stage["depends_on"])
                job = _receipt(project, dep)
                if not job or job.get("review", {}).get("decision") != "accepted":
                    return {"state": "awaiting_review", "stage": dep["id"]}
            if receipt is None:
                receipt = {"id": uuid.uuid4().hex, "stage_id": stage["id"], "fingerprint": stage["fingerprint"],
                           "model": stage["model"], "request": copy.deepcopy(stage), "state": "submitting", "created_at": _now()}
                project["jobs"].append(receipt)
                atomic_json(path, project)
            def checkpoint(task_id, request=None):
                if request is not None:
                    receipt["validated_request"] = request
                if task_id:
                    receipt.update(task_id=task_id, state="submitted")
                atomic_json(path, project)
            try:
                result = runner({**stage, "task_id": receipt.get("task_id")}, checkpoint)
                if result.get("state") not in SUCCESS_STATES:
                    receipt.update(state="failed", error=result.get("error", "provider task failed"))
                else:
                    artifacts = []
                    for file in result.get("files", []):
                        asset = Path(file).resolve()
                        if not asset.is_file() or not asset.stat().st_size:
                            raise ValueError("Generation has no persistent nonempty asset")
                        stored_path = asset.relative_to(path.parent).as_posix() if asset.is_relative_to(path.parent) else str(asset)
                        artifacts.append({"path": stored_path, "sha256": file_hash(asset), "bytes": asset.stat().st_size})
                    if not artifacts:
                        raise ValueError("Generation returned no downloaded artifacts")
                    receipt.update(state="success", artifacts=artifacts, completed_at=_now(),
                                   task_id=result.get("task_id") or receipt.get("task_id"),
                                   credits_consumed=result.get("credits_consumed"))
                atomic_json(path, project)
                if receipt["state"] == "failed":
                    return {"state": "needs_changes", "stage": stage["id"]}
            except Exception as exc:
                receipt.update(state="submitted" if receipt.get("task_id") else "needs_recovery", error=str(exc))
                atomic_json(path, project)
                return {"state": "pending" if receipt.get("task_id") else "needs_recovery", "stage": stage["id"], "error": str(exc)}
        reviews = [s["id"] for s in stages if (_receipt(project, s) or {}).get("review", {}).get("decision") != "accepted"]
        return {"state": "awaiting_review" if reviews else "completed", "review_stages": reviews,
                "project": str(path), "new_jobs": len(needed)}


def review_stage(path: Path, stage_id: str, decision: str, note: str) -> dict:
    path = path.expanduser().resolve()
    if decision not in {"accepted", "rejected"} or not note.strip():
        raise ValueError("Review needs accepted/rejected and a substantive note")
    with manifest_lock(path):
        project = _read(path)
        stage = next((s for s in _stages(project) if s["id"] == stage_id), None)
        job = _receipt(project, stage) if stage else None
        if not job or job["state"] != "success" or not _asset_valid(path.parent, job):
            raise ValueError("Review requires an unchanged completed asset")
        job["review"] = {"decision": decision, "note": note, "at": _now()}
        atomic_json(path, project)
    return job["review"]


def recover_job(path: Path, job_id: str, task_id: str) -> dict:
    path = path.expanduser().resolve()
    if not task_id.strip():
        raise ValueError("Recovery needs a verified provider task ID; never mark an unknown submission free to retry")
    with manifest_lock(path):
        project = _read(path)
        job = next((j for j in project["jobs"] if j["id"] == job_id), None)
        if not job or job["state"] not in {"submitting", "needs_recovery"}:
            raise ValueError("Only an ambiguous submission may be attached to a known task")
        job.update(task_id=task_id, state="submitted", recovered_at=_now())
        atomic_json(path, project)
    return {"state": "submitted", "task_id": task_id}


def storyboard(path: Path) -> Path:
    path = path.expanduser().resolve()
    project = _read(path)
    cards = []
    for shot in project["shots"]:
        media = []
        for stage in _stages(project):
            if not stage["id"].startswith(shot["id"] + "."):
                continue
            job = _receipt(project, stage)
            if job and _asset_valid(path.parent, job):
                file = (path.parent / job["artifacts"][0]["path"]).resolve()
                url = html.escape(file.as_uri(), quote=True)
                tag = "img" if stage["kind"] == "image" else ("video" if stage["kind"] == "video" else "audio")
                media.append(f'<{tag} src="{url}" controls></{tag}>')
        cards.append(f'<article><h2>{html.escape(shot["id"])} · {shot["duration"]}s</h2>'+"".join(media)+
                     f'<p>{html.escape(shot["prompt"])}</p><p>Motion: {html.escape(shot["motion"])}</p>'+
                     f'<p>Narration: {html.escape(shot["narration"])}</p></article>')
    target = path.parent / "storyboard.html"
    target.write_text('<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>KIE Media Storyboard</title><style>body{font:17px system-ui;background:#101723;color:#edf5ff;margin:40px}'
        'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}article{background:#1c293a;padding:24px;border-radius:16px}'
        'img,video,audio{width:100%;max-height:300px;object-fit:contain}p{line-height:1.6}</style>'+
        f'<h1>{html.escape(project["brief"])}</h1><p>Revision {project["revision"]}</p><main>'+"".join(cards)+"</main></html>", encoding="utf-8")
    return target


def import_asset(path: Path, stage_id: str, source: Path) -> dict:
    """Explicitly attach existing media, without claiming a provider generation."""
    path, source = path.expanduser().resolve(), source.expanduser().resolve()
    from .media import probe
    with manifest_lock(path):
        project = _read(path)
        stage = next((s for s in _stages(project) if s["id"] == stage_id), None)
        if stage is None:
            raise ValueError("Unknown stage")
        if _receipt(project, stage):
            raise ValueError("Stage already has a receipt; edit its specification before importing a replacement")
        info = probe(source)
        expected = stage["kind"] if stage["kind"] in {"image", "video"} else "audio"
        if not info[expected]:
            raise ValueError(f"Expected {expected} media for this stage")
        checksum = file_hash(source)
        target = path.parent / "assets" / (checksum + source.suffix.lower())
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
        receipt = {"id": uuid.uuid4().hex, "stage_id": stage_id, "fingerprint": stage["fingerprint"],
                   "state": "success", "origin": "imported", "created_at": _now(),
                   "artifacts": [{"path": target.relative_to(path.parent).as_posix(), "sha256": checksum, "bytes": target.stat().st_size}]}
        project["jobs"].append(receipt)
        atomic_json(path, project)
        return receipt


def render_project(path: Path, *, captions=False) -> dict:
    from .media import assemble_timeline
    path = path.expanduser().resolve()
    with manifest_lock(path):
        project = _read(path)
        stages = _stages(project)
        receipts = {}
        for stage in stages:
            if stage["kind"] == "image":
                continue
            receipt = _receipt(project, stage)
            if not receipt or receipt.get("state") != "success" or not _asset_valid(path.parent, receipt):
                raise ValueError(f"Missing or changed asset: {stage['id']}")
            if receipt.get("review", {}).get("decision") != "accepted":
                raise ValueError(f"Review required: {stage['id']}")
            receipts[stage["id"]] = receipt
        signature = digest({"assets": {key: r["artifacts"] for key, r in receipts.items()},
                            "shots": project["shots"], "aspect_ratio": project["aspect_ratio"], "captions": captions})
        previous = project.get("renders", {}).get(signature)
        if previous:
            output = path.parent / previous["path"]
            if not output.is_file() or file_hash(output) != previous["sha256"]:
                raise ValueError("Previous render changed; preserve it and choose a new project revision")
            return {**previous, "file": str(output), "reused": True}
        shots = []
        for shot in project["shots"]:
            video = receipts[shot["id"] + ".video"]
            row = {"video": str(path.parent / video["artifacts"][0]["path"]),
                   "duration": shot["duration"], "narration": shot["narration"]}
            if shot["id"] + ".voice" in receipts:
                row["voice"] = str(path.parent / receipts[shot["id"] + ".voice"]["artifacts"][0]["path"])
            shots.append(row)
        music = str(path.parent / receipts["music"]["artifacts"][0]["path"]) if "music" in receipts else None
        output = path.parent / "renders" / f"film-{signature[:16]}.mp4"
        if output.exists():
            # An interrupted local render may have written a file before its
            # receipt. Preserve it and render to a fresh path; no paid job runs.
            output = output.with_name(f"film-{signature[:16]}-{uuid.uuid4().hex[:8]}.mp4")
        result = assemble_timeline(shots, output, aspect_ratio=project["aspect_ratio"], music=music, captions=captions)
        stored = {**result, "path": output.relative_to(path.parent).as_posix(), "sha256": file_hash(output), "created_at": _now()}
        project.setdefault("renders", {})[signature] = stored
        atomic_json(path, project)
        return {**stored, "reused": False}


def production_report(path: Path) -> dict:
    path = path.expanduser().resolve()
    project = _read(path)
    costs = [j.get("credits_consumed") for j in project["jobs"]]
    known = [c for c in costs if isinstance(c, (float, int)) and not isinstance(c, bool) and math.isfinite(c)]
    return {**_plan(project, path.parent), "recorded_jobs": len(project["jobs"]),
            "known_credits_consumed": sum(known), "jobs_without_cost_observation": len(costs) - len(known),
            "costs_complete": len(known) == len(costs), "changes": project["changes"],
            "jobs": project["jobs"], "renders": project.get("renders", {}),
            "note": "Technical checks and recorded reviews are evidence, not a guarantee of visual identity."}


def export_project(path: Path, output: Path) -> dict:
    import zipfile
    path, output = path.expanduser().resolve(), output.expanduser().resolve()
    with manifest_lock(path):
        project = _read(path)
        if any(j["state"] in {"submitting", "submitted", "needs_recovery"} for j in project["jobs"]):
            raise ValueError("Resolve active/ambiguous jobs before exporting a handoff")
        if output.exists():
            raise ValueError("Export target already exists")
        files = {}
        records = list(project["entities"].values())
        records += [a for j in project["jobs"] for a in j.get("artifacts", [])]
        records += list(project.get("renders", {}).values())
        for asset in records:
            original = path.parent / asset["path"]
            if not original.is_file() or file_hash(original) != asset["sha256"]:
                raise ValueError(f"Changed or missing export asset: {original.name}")
            name = "assets/" + asset["sha256"] + original.suffix.lower()
            files[name] = original
            asset["path"] = name
            if "file" in asset:
                asset["file"] = name
            if asset.get("subtitles"):
                subtitle = Path(asset["subtitles"])
                if not subtitle.is_absolute():
                    subtitle = path.parent / subtitle
                if subtitle.is_file():
                    subname = "assets/" + file_hash(subtitle) + ".srt"
                    files[subname] = subtitle
                    asset["subtitles"] = subname
        # Render cache signatures include old local paths. Recompute on the
        # receiving host, retaining the original render receipts in the dossier.
        project["exported_renders"] = project.pop("renders", {})
        project["handoff"] = {"at": _now(), "source_revision": project["revision"], "assets": len(files)}
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_name(output.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with zipfile.ZipFile(temp, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("project.json", json.dumps(project, ensure_ascii=False, indent=2))
                for name, original in sorted(files.items()):
                    archive.write(original, name)
            temp.replace(output)
        finally:
            temp.unlink(missing_ok=True)
        return {"file": str(output), "sha256": file_hash(output), "assets": len(files), "revision": project["revision"]}

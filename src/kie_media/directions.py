"""Free creative branches and scene selection; production uses the project runner."""
from __future__ import annotations

import copy
import html
import json
import shutil
import tempfile
import uuid
from contextlib import ExitStack
from pathlib import Path

from .agent import manifest_lock
from .projects import _read, _stages, _receipt, _plan, _validate, _now, file_hash
from .storage import atomic_json


STYLES = {
    "calm": {
        "label": "Calm / Ruhig", "visual": "Quiet editorial framing, soft natural light, restrained palette, generous negative space. Preserve the supplied subject and product details.",
        "motion": "Gentle slow dolly, stable framing and restrained ambient motion; no sudden cuts.",
    },
    "playful": {
        "label": "Playful / Verspielt", "visual": "Playful graphic composition, bright complementary accents, unexpected but credible arrangement. Preserve the supplied subject and product details.",
        "motion": "A light, smooth lateral reveal with playful timing; preserve geometry and avoid abrupt motion.",
    },
    "dramatic": {
        "label": "Dramatic / Dramatisch", "visual": "Dramatic side lighting, controlled deep shadows, cinematic close emphasis and a strong focal hierarchy. Preserve the supplied subject and product details.",
        "motion": "Deliberate cinematic push-in with a subtle low-angle reveal; stable subject and coherent motion.",
    },
}
ACTIVE = {"submitting", "submitted", "needs_recovery"}
SETTINGS = ("aspect_ratio", "models", "voice", "music_prompt")


def _idle(project: dict) -> None:
    if any(job["state"] in ACTIVE for job in project["jobs"]):
        raise ValueError("Resolve active or ambiguous jobs before branching or selecting scenes")


def _asset(source_root: Path, record: dict, target_root: Path | None) -> dict:
    source = (source_root / record["path"]).resolve()
    checksum = record["sha256"]
    if not source.is_file() or file_hash(source) != checksum:
        raise ValueError(f"Asset changed or missing: {source.name}")
    suffix = source.suffix.lower()
    # Generated assets get ordinary extensions; no path text from receipts is
    # used to construct directories in the destination.
    relative = f"assets/{checksum}{suffix}"
    if target_root is not None:
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if file_hash(target) != checksum:
                raise ValueError("Destination asset checksum conflict")
        else:
            shutil.copyfile(source, target)
            if file_hash(target) != checksum:
                raise ValueError("Asset changed while being copied")
    return {**copy.deepcopy(record), "path": relative}


def _settings(project: dict) -> dict:
    return {key: project.get(key) for key in SETTINGS}


def _clone(source: dict, source_root: Path, target_root: Path) -> dict:
    """Copy a settled project into an independent content-addressed workspace."""
    result = copy.deepcopy(source)
    result.update(id=uuid.uuid4().hex, revision=1, created_at=_now(), changes=[], jobs=[])
    for key in ("renders", "exported_renders", "handoff", "selection", "direction"):
        result.pop(key, None)
    result["entities"] = {name: _asset(source_root, ref, target_root) for name, ref in source["entities"].items()}
    old_stages = {s["id"]: s for s in _stages(source)}
    for stage in _stages(result):
        job = _receipt(source, old_stages[stage["id"]])
        if not job:
            continue
        copied = copy.deepcopy(job)
        copied["artifacts"] = [_asset(source_root, a, target_root) for a in job.get("artifacts", [])]
        copied["source_fingerprint"] = copied["fingerprint"]
        copied["fingerprint"] = stage["fingerprint"]
        copied["reused_from"] = {"project_id": source["id"], "revision": source["revision"], "job_id": job["id"]}
        result["jobs"].append(copied)
    return result


def create_directions(source: Path, output_dir: Path) -> dict:
    source, output_dir = source.expanduser().resolve(), output_dir.expanduser().resolve()
    with manifest_lock(source), manifest_lock(output_dir.parent / (output_dir.name + ".build")):
        project = _read(source)
        _idle(project)
        if output_dir.exists():
            raise ValueError("Directions destination already exists; use its saved projects or choose a new folder")
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        # Publish the entire collection by one rename. A partial copy is never
        # presented as a ready directions manifest.
        with tempfile.TemporaryDirectory(prefix=".kie-directions-", dir=output_dir.parent) as temp:
            stage_root = Path(temp).resolve()
            if not stage_root.is_relative_to(output_dir.parent):
                raise ValueError("Invalid staging directory")
            collection = {"format": "kie-media-directions", "version": 1, "id": uuid.uuid4().hex,
                "created_at": _now(), "source_project_id": project["id"], "source_revision": project["revision"],
                "brief": project["brief"], "scene_order": [s["id"] for s in project["shots"]], "directions": {}}
            image_jobs = 0
            for name, style in STYLES.items():
                member_root = stage_root / name
                variant = _clone(project, source.parent, member_root)
                variant["direction"] = {"name": name, "label": style["label"], "source_project_id": project["id"],
                                        "method": "editable deterministic style brief; no model call"}
                for shot in variant["shots"]:
                    shot["prompt"] += "\nVisual direction: " + style["visual"]
                    shot["motion"] += "\nCamera direction: " + style["motion"]
                _validate(variant)
                atomic_json(member_root / "project.json", variant)
                image_jobs += sum(s["kind"] == "image" and s["state"] == "pending" for s in _plan(variant, member_root)["stages"])
                collection["directions"][name] = {"label": style["label"], "project": f"{name}/project.json", "project_id": variant["id"]}
            atomic_json(stage_root / "directions.json", collection)
            stage_root.rename(output_dir)
    return {"file": str(output_dir / "directions.json"), "directions": collection["directions"],
            "new_image_jobs": image_jobs, "paid_requests": 0,
            "note": "Planning is free. Generate image previews explicitly with project run and a job cap."}


def _collection(path: Path) -> tuple[dict, dict[str, Path]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != "kie-media-directions" or data.get("version") != 1:
        raise ValueError("Unsupported directions collection")
    if not isinstance(data.get("directions"), dict) or not isinstance(data.get("scene_order"), list):
        raise ValueError("Invalid directions collection")
    members = {}
    for name, item in data.get("directions", {}).items():
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ("project", "project_id", "label")):
            raise ValueError("Invalid direction project entry")
        target = (path.parent / item["project"]).resolve()
        if not target.is_relative_to(path.parent) or target == path:
            raise ValueError("Direction project must remain inside the collection")
        members[name] = target
    order = data.get("scene_order", [])
    if not members or not order or any(not isinstance(s, str) for s in order) or len(order) != len(set(order)):
        raise ValueError("Invalid directions collection")
    return data, members


def _selected(collection: dict, members: dict, picks: dict, projects: dict, output_root: Path | None) -> tuple[dict, dict]:
    order = collection["scene_order"]
    if not isinstance(picks, dict) or set(picks) != set(order):
        raise ValueError("Select exactly one direction for every scene")
    if any(not isinstance(name, str) or name not in members for name in picks.values()):
        raise ValueError("Unknown selected direction")
    chosen_names = list(dict.fromkeys(picks.values()))
    first = projects[picks[order[0]]]
    for name in chosen_names:
        project = projects[name]
        _idle(project)
        if project["id"] != collection["directions"][name]["project_id"]:
            raise ValueError("Direction project identity does not match its collection")
        if _settings(project) != _settings(first):
            raise ValueError("Selected directions have conflicting project settings; align models, format, voice and music first")
    result = {key: copy.deepcopy(value) for key, value in first.items()
              if key not in {"shots", "entities", "jobs", "renders", "exported_renders", "handoff", "direction", "selection"}}
    result.update(id=uuid.uuid4().hex, revision=1, created_at=_now(), changes=[], shots=[], entities={}, jobs=[])
    sources = {}
    for scene in order:
        name = picks[scene]
        project = projects[name]
        shot = next((s for s in project["shots"] if s["id"] == scene), None)
        if shot is None:
            raise ValueError(f"Selected direction has no scene {scene}")
        result["shots"].append(copy.deepcopy(shot))
        for entity in shot["entities"]:
            ref = _asset(members[name].parent, project["entities"][entity], output_root)
            if entity in result["entities"] and ref != result["entities"][entity]:
                raise ValueError(f"Entity {entity} differs between selected directions; align the references")
            result["entities"][entity] = ref
        sources[scene] = name
    new_stages = _stages(result)
    reused = []
    for stage in new_stages:
        # Music is shared under the checked global settings. Prefer an existing
        # successful soundtrack from a selected direction, never order it twice.
        names = chosen_names if stage["kind"] == "music" else [sources[stage["id"].rsplit(".", 1)[0]]]
        found = []
        for name in names:
            original_stage = next((s for s in _stages(projects[name]) if s["id"] == stage["id"]), None)
            if stage["kind"] == "music" and original_stage and original_stage["fingerprint"] != stage["fingerprint"]:
                continue
            job = _receipt(projects[name], original_stage) if original_stage else None
            if job:
                found.append((name, job))
        if not found:
            continue
        name, job = next(((n, j) for n, j in found if j["state"] == "success" and j.get("review", {}).get("decision") != "rejected"), found[0])
        if job["state"] != "success" or job.get("review", {}).get("decision") == "rejected":
            raise ValueError(f"Selected stage {stage['id']} failed or was rejected; fix or review it first")
        if not job.get("artifacts"):
            raise ValueError(f"Selected stage {stage['id']} has no artifacts")
        receipt = copy.deepcopy(job)
        receipt["artifacts"] = [_asset(members[name].parent, a, output_root) for a in job["artifacts"]]
        receipt["source_fingerprint"] = job["fingerprint"]
        receipt["fingerprint"] = stage["fingerprint"]
        receipt["reused_from"] = {"direction": name, "project_id": projects[name]["id"], "revision": projects[name]["revision"], "job_id": job["id"]}
        result["jobs"].append(receipt)
        reused.append({"stage": stage["id"], "direction": name, "task_id": receipt.get("task_id"), "review": receipt.get("review")})
    _validate(result)
    imported_videos = {j["stage_id"] for j in result["jobs"] if j.get("origin") == "imported" and j["state"] == "success"}
    pending = [s["id"] for s in new_stages if _receipt(result, s) is None
               and not (s["kind"] == "image" and s["id"].removesuffix(".image") + ".video" in imported_videos)]
    result["selection"] = {"collection_id": collection["id"], "at": _now(), "picks": picks,
                           "source_revisions": {n: projects[n]["revision"] for n in chosen_names}}
    return result, {"picks": picks, "new_jobs": len(pending), "pending_stages": pending, "reused_stages": reused,
                    "paid_requests": 0, "note": "Selection does not generate media; existing reviews are preserved, not invented."}


def compose_directions(collection_path: Path, picks: dict, output: Path, *, dry_run=False) -> dict:
    collection_path, output = collection_path.expanduser().resolve(), output.expanduser().resolve()
    collection, members = _collection(collection_path)
    if not isinstance(picks, dict) or set(picks) != set(collection["scene_order"]):
        raise ValueError("Select exactly one direction for every scene")
    if any(not isinstance(name, str) or name not in members for name in picks.values()):
        raise ValueError("Unknown selected direction")
    if output == collection_path or output in members.values():
        raise ValueError("Compose into a new project, not a source direction")
    selected_paths = {members[name] for name in picks.values()}
    with ExitStack() as stack:
        for path in sorted(selected_paths, key=lambda p: str(p).casefold()):
            stack.enter_context(manifest_lock(path))
        projects = {name: _read(members[name]) for name in set(picks.values())}
        _, preview = _selected(collection, members, picks, projects, None)
        if dry_run:
            return {**preview, "dry_run": True, "output": str(output)}
        # All source validations precede the first destination write.
        with manifest_lock(output):
            if output.exists():
                raise ValueError("Winner project already exists; edit/resume it or choose a new path")
            result, summary = _selected(collection, members, picks, projects, output.parent)
            atomic_json(output, result)
    return {**summary, "dry_run": False, "output": str(output)}


def compare_directions(collection_path: Path) -> dict:
    collection_path = collection_path.expanduser().resolve()
    collection, members = _collection(collection_path)
    with ExitStack() as stack:
        for path in sorted(set(members.values()), key=lambda p: str(p).casefold()):
            stack.enter_context(manifest_lock(path))
        projects = {name: _read(path) for name, path in members.items()}
        rows = []
        for scene in collection["scene_order"]:
            cards = []
            options = []
            for name, project in projects.items():
                shot = next((s for s in project["shots"] if s["id"] == scene), None)
                if shot is None:
                    raise ValueError(f"Direction {name} has no scene {scene}")
                label = collection["directions"][name]["label"]
                options.append(f'<option value="{html.escape(name, quote=True)}">{html.escape(label)}</option>')
                media, state = "", "Planned · no preview generated"
                for kind in ("video", "image"):
                    stage = next(s for s in _stages(project) if s["id"] == scene + "." + kind)
                    job = _receipt(project, stage)
                    if job and job["state"] == "success" and job.get("artifacts"):
                        ref = job["artifacts"][0]
                        _asset(members[name].parent, ref, None)
                        url = html.escape((members[name].parent / ref["path"]).resolve().as_uri(), quote=True)
                        media = f'<img src="{url}" alt="{html.escape(label, quote=True)} preview">' if kind == "image" else f'<video controls src="{url}"></video>'
                        state = "Review: " + job.get("review", {}).get("decision", "not recorded")
                        break
                cards.append(f'<article><h3>{html.escape(label)}</h3><div class="preview">{media or "Preview pending"}</div>'
                             f'<p class="state">{html.escape(state)}</p><p>{html.escape(shot["prompt"])}</p>'
                             f'<details><summary>Camera / motion</summary><p>{html.escape(shot["motion"])}</p></details></article>')
            rows.append(f'<section><header><h2>{html.escape(scene)}</h2><label>Use direction <select data-scene="{html.escape(scene, quote=True)}">'
                        + "".join(options) + '</select></label></header><div class="grid">' + "".join(cards) + '</div></section>')
        target = collection_path.parent / "comparison.html"
        payload = json.dumps({"collection_id": collection["id"]}, ensure_ascii=True).replace("<", "\\u003c")
        document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KIE Media · Creative directions</title><style>
*{box-sizing:border-box}body{margin:0;background:#0d1420;color:#eaf1fb;font:16px system-ui;line-height:1.55}main{max-width:1420px;margin:auto;padding:32px}
h1{font-size:clamp(28px,4vw,48px);line-height:1.12}h2,h3{margin:0}h3{font-size:18px}.intro{max-width:850px;color:#b3c4d9}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}
section{margin:36px 0}header{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:14px}article{background:#172335;padding:20px;border:1px solid #30415a;border-radius:16px;overflow-wrap:anywhere}
.preview{margin-top:16px;aspect-ratio:16/9;display:grid;place-items:center;background:#101926;border-radius:10px;color:#9cacc0;overflow:hidden}img,video{width:100%;height:100%;object-fit:contain}.state{font-size:13px;color:#98e5d4}select,button{font:inherit;border-radius:8px;padding:10px 16px;border:1px solid #49708e;background:#1c3047;color:#f4f8fd}button{background:#85e1cc;color:#102a2d;font-weight:700;cursor:pointer}.footer{position:sticky;bottom:0;padding:16px;background:#101d2ff5;border-top:1px solid #30415a}code{display:block;white-space:pre-wrap;margin-top:12px;font-size:13px}details{color:#b3c4d9}@media(max-width:850px){.grid{grid-template-columns:1fr}header{align-items:flex-start;flex-direction:column}main{padding:20px}}
</style><main><p>KIE MEDIA / CREATIVE DIRECTIONS</p>'''
        document += f'<h1>{html.escape(collection["brief"])}</h1><p class="intro">Compare three editable visual directions. Choose one per scene. '
        document += 'Downloading a selection does not generate or approve media. Review checks still apply.</p>' + "".join(rows)
        document += '''<div class="footer"><button id="save">Download selection.json</button><code>kie-media project compose directions.json --selection-file selection.json --output winner/project.json --dry-run --json</code></div></main>'''
        document += '<script>const meta=' + payload + ''';
document.getElementById('save').addEventListener('click',()=>{
const picks=Object.fromEntries(Array.from(document.querySelectorAll('select[data-scene]')).map(el=>[el.dataset.scene,el.value]));
const url=URL.createObjectURL(new Blob([JSON.stringify({...meta,picks},null,2)],{type:'application/json'}));
const a=document.createElement('a');a.href=url;a.download='selection.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});</script></html>'''
        target.write_text(document, encoding="utf-8")
    return {"file": str(target), "paid_requests": 0}

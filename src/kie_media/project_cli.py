"""Project command surface shared by human users and agent hosts."""
from pathlib import Path


def add_parser(sub):
    parser = sub.add_parser("project", help="Plan, produce, review and selectively edit scene projects")
    commands = parser.add_subparsers(dest="project_command", required=True)
    init = commands.add_parser("init")
    init.add_argument("path", type=Path)
    init.add_argument("brief")
    init.add_argument("--shots", type=int, default=3)
    init.add_argument("--aspect-ratio", default="16:9")
    init.add_argument("--image-model", default="image-fast")
    init.add_argument("--video-model", default="video-kling-image")
    for name in ("plan", "storyboard", "report"):
        cmd = commands.add_parser(name)
        cmd.add_argument("path", type=Path)
    edit = commands.add_parser("edit")
    edit.add_argument("path", type=Path)
    edit.add_argument("shot")
    for field in ("prompt", "motion", "narration"):
        edit.add_argument("--" + field)
    edit.add_argument("--duration", type=float)
    edit.add_argument("--take", type=int)
    edit.add_argument("--entity", action="append", dest="entities")
    edit.add_argument("--dry-run", action="store_true")
    entity = commands.add_parser("entity")
    entity.add_argument("path", type=Path)
    entity.add_argument("name")
    entity.add_argument("file", type=Path)
    entity.add_argument("--description", default="")
    settings = commands.add_parser("configure")
    settings.add_argument("path", type=Path)
    settings.add_argument("--music-prompt")
    settings.add_argument("--voice")
    for kind in ("image", "video", "voice", "music"):
        settings.add_argument("--" + kind + "-model")
    run = commands.add_parser("run")
    run.add_argument("path", type=Path)
    run.add_argument("--phase", choices=["images", "videos", "audio", "all"], default="images")
    run.add_argument("--max-jobs", type=int, default=5)
    review = commands.add_parser("review")
    review.add_argument("path", type=Path)
    review.add_argument("stage")
    review.add_argument("decision", choices=["accepted", "rejected"])
    review.add_argument("--note", required=True)
    recover = commands.add_parser("recover")
    recover.add_argument("path", type=Path)
    recover.add_argument("job_id")
    recover.add_argument("--task-id", required=True)
    imported = commands.add_parser("import")
    imported.add_argument("path", type=Path)
    imported.add_argument("stage")
    imported.add_argument("file", type=Path)
    render = commands.add_parser("render")
    render.add_argument("path", type=Path)
    render.add_argument("--captions", action="store_true")
    export = commands.add_parser("export")
    export.add_argument("path", type=Path)
    export.add_argument("output", type=Path)
    directions = commands.add_parser("directions", help="Create three editable visual directions without generation")
    directions.add_argument("path", type=Path)
    directions.add_argument("--output-dir", required=True, type=Path)
    compare = commands.add_parser("compare", help="Write an interactive direction comparison with scene choices")
    compare.add_argument("path", type=Path, help="directions.json")
    compose = commands.add_parser("compose", help="Combine chosen scenes into a new project")
    compose.add_argument("path", type=Path, help="directions.json")
    selection = compose.add_mutually_exclusive_group(required=True)
    selection.add_argument("--pick", action="append", help="SCENE=DIRECTION; repeat once per scene")
    selection.add_argument("--selection-file", type=Path)
    compose.add_argument("--output", type=Path, required=True)
    compose.add_argument("--dry-run", action="store_true")
    for command in commands.choices.values():
        command.add_argument("--json", action="store_true")


def dispatch(args):
    from . import projects
    name = args.project_command
    if name in {"directions", "compare", "compose"}:
        from .directions import create_directions, compare_directions, compose_directions
        if name == "directions":
            return create_directions(args.path, args.output_dir)
        if name == "compare":
            return compare_directions(args.path)
        import json
        if args.selection_file:
            selection = json.loads(args.selection_file.read_text(encoding="utf-8"))
            collection = json.loads(args.path.read_text(encoding="utf-8"))
            if not isinstance(selection, dict) or selection.get("collection_id") != collection.get("id"):
                raise ValueError("Selection file belongs to a different directions collection")
            picks = selection.get("picks")
        else:
            picks = {}
            for value in args.pick:
                scene, separator, direction = value.partition("=")
                if not separator or not scene or not direction or scene in picks:
                    raise ValueError("Each --pick must be a unique SCENE=DIRECTION")
                picks[scene] = direction
        return compose_directions(args.path, picks, args.output, dry_run=args.dry_run)
    if name == "init":
        return projects.create_project(args.path, args.brief, shots=args.shots, aspect_ratio=args.aspect_ratio,
                                       image_model=args.image_model, video_model=args.video_model)
    if name == "plan":
        return projects.project_plan(args.path)
    if name == "report":
        return projects.production_report(args.path)
    if name == "export":
        return projects.export_project(args.path, args.output)
    if name == "edit":
        changes = {key: getattr(args, key) for key in ("prompt", "motion", "narration", "duration", "take", "entities") if getattr(args, key) is not None}
        return projects.revise_shot(args.path, args.shot, changes, dry_run=args.dry_run)
    if name == "entity":
        return projects.add_entity(args.path, args.name, args.file, args.description)
    if name == "configure":
        models = {kind: getattr(args, kind + "_model") for kind in ("image", "video", "voice", "music") if getattr(args, kind + "_model")}
        return projects.configure_project(args.path, music_prompt=args.music_prompt, voice=args.voice, models=models)
    if name == "run":
        from .cli import _load_env_key
        from .client import KieClient
        return projects.run_project(args.path, phase=args.phase, max_jobs=args.max_jobs,
                                    client=KieClient(_load_env_key(args.env_file) or ""))
    if name == "review":
        return projects.review_stage(args.path, args.stage, args.decision, args.note)
    if name == "recover":
        return projects.recover_job(args.path, args.job_id, args.task_id)
    if name == "import":
        return projects.import_asset(args.path, args.stage, args.file)
    if name == "render":
        return projects.render_project(args.path, captions=args.captions)
    if name == "storyboard":
        return {"file": str(projects.storyboard(args.path))}
    raise ValueError("Unknown project command")

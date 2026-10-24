"""Explicit plan/run/recover/review commands for source-video transformations."""
from pathlib import Path


def add_parser(sub):
    parser = sub.add_parser("recast", help="Transform an existing clip with documented KIE video models")
    commands = parser.add_subparsers(dest="recast_command", required=True)
    plan = commands.add_parser("plan", help="Validate local source/references without upload or spend")
    plan.add_argument("prompt")
    plan.add_argument("--video", required=True, type=Path)
    plan.add_argument("--reference-image", action="append", default=[], type=Path)
    plan.add_argument("--mode", choices=["motion-transfer", "object-swap", "restyle"], default="motion-transfer")
    plan.add_argument("--resolution", default="720p")
    plan.add_argument("--duration", type=int)
    plan.add_argument("--keep-original-sound", action="store_true")
    plan.add_argument("--take", type=int, default=1, help="Increment deliberately for a new paid variation")
    plan.add_argument("--save", type=Path, help="Atomically save the exact validated plan")
    run = commands.add_parser("run", help="Execute a saved plan or resume its task")
    run.add_argument("path", type=Path, help="Saved recast plan JSON")
    run.add_argument("--manifest", type=Path, help="Default: recast-<fingerprint>-run.json beside the plan")
    run.add_argument("--max-jobs", type=int, required=True)
    recover = commands.add_parser("recover", help="Attach a known task after ambiguous creation")
    recover.add_argument("path", type=Path)
    recover.add_argument("--task-id", required=True)
    review = commands.add_parser("review")
    review.add_argument("path", type=Path)
    review.add_argument("decision", choices=["accepted", "rejected"])
    review.add_argument("--note", required=True)
    for name in ("report", "compare"):
        command = commands.add_parser(name)
        command.add_argument("path", type=Path)
    capabilities = commands.add_parser("capabilities", help="Show documented modes, models and constraints offline")
    capabilities.add_argument("--mode", choices=["motion-transfer", "object-swap", "restyle"])
    for command in commands.choices.values():
        command.add_argument("--json", action="store_true")


def dispatch(args):
    import json
    from . import recast
    from .storage import atomic_json
    name = args.recast_command
    if name == "capabilities":
        from .recast_models import recast_capabilities
        modes = [args.mode] if args.mode else ["motion-transfer", "object-swap", "restyle"]
        return {"modes": {mode: recast_capabilities(mode) for mode in modes}, "paid_requests": 0}
    if name == "plan":
        result = recast.build_recast_plan(args.video, args.prompt, references=args.reference_image,
            mode=args.mode, duration=args.duration, resolution=args.resolution,
            keep_original_sound=args.keep_original_sound, take=args.take)
        if args.save:
            path = args.save.expanduser().resolve()
            with recast.manifest_lock(path):
                if path.exists():
                    raise ValueError("Plan file exists; choose a new filename")
                atomic_json(path, result)
        return result
    if name == "run":
        from .cli import _load_env_key
        from .client import KieClient
        path = args.path.expanduser().resolve()
        plan = json.loads(path.read_text(encoding="utf-8"))
        recast._validate_plan(plan)
        manifest = args.manifest or path.parent / ("recast-" + plan["fingerprint"][:16] + "-run.json")
        return recast.run_recast(plan, manifest, max_jobs=args.max_jobs,
                                 client=KieClient(_load_env_key(args.env_file) or ""))
    if name == "recover":
        return recast.recover_recast(args.path, args.task_id)
    if name == "review":
        return recast.review_recast(args.path, args.decision, args.note)
    if name == "compare":
        return recast.compare_recast(args.path)
    if name == "report":
        return recast.load_recast_manifest(args.path)
    raise ValueError("Unknown recast command")

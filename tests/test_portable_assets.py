import json
import subprocess
import sys
import unittest
from pathlib import Path

import jsonschema
from referencing import Registry, Resource

from kie_media.agent import build_plan
from scripts.evaluate_planner import evaluate


ROOT = Path(__file__).resolve().parents[1]


class PortableAssetsTests(unittest.TestCase):
    def test_agent_discovery_adapters_point_to_one_canonical_skill(self):
        canonical = ROOT / "skills" / "kie-media" / "SKILL.md"
        self.assertTrue(canonical.is_file())
        canonical_text = canonical.read_text(encoding="utf-8")
        self.assertNotIn("/home/benny", canonical_text)
        self.assertIn("name: kie-media", canonical_text)
        for adapter in [
            ROOT / ".agents" / "skills" / "kie-media" / "SKILL.md",
            ROOT / ".claude" / "skills" / "kie-media" / "SKILL.md",
        ]:
            text = adapter.read_text(encoding="utf-8")
            self.assertIn("../../../skills/kie-media/SKILL.md", text)

    def test_json_schemas_are_valid_json_and_cover_real_payloads(self):
        plan_schema = json.loads((ROOT / "schemas" / "production-plan.schema.json").read_text())
        manifest_schema = json.loads((ROOT / "schemas" / "run-manifest.schema.json").read_text())
        plan = build_plan("One icon", workflow="image").to_dict()
        self.assertFalse(set(plan_schema["required"]) - set(plan))
        self.assertEqual(manifest_schema["properties"]["plan"]["$ref"], "production-plan.schema.json")

    def test_json_schemas_validate_real_plan_and_manifest_shapes(self):
        plan_schema = json.loads((ROOT / "schemas" / "production-plan.schema.json").read_text())
        manifest_schema = json.loads((ROOT / "schemas" / "run-manifest.schema.json").read_text())
        validator_class = jsonschema.validators.validator_for(plan_schema)
        validator_class.check_schema(plan_schema)
        validator_class.check_schema(manifest_schema)
        plan_validator = validator_class(plan_schema)
        scenarios = json.loads((ROOT / "evals" / "scenarios.json").read_text())
        plans = [build_plan(case["brief"], **case.get("options", {})).to_dict() for case in scenarios]
        for plan in plans:
            plan_validator.validate(plan)
        plan = plans[0]
        registry = Registry().with_resource(
            plan_schema["$id"], Resource.from_contents(plan_schema)
        )
        manifest = {
            "plan_fingerprint": "a" * 64,
            "plan": plan,
            "execution": {"state": "planned", "results": []},
        }
        jsonschema.validators.validator_for(manifest_schema)(
            manifest_schema, registry=registry
        ).validate(manifest)
        self.assertEqual(plan["estimated_jobs"], 1)

    def test_offline_planner_eval_suite_passes(self):
        report = evaluate(ROOT / "evals" / "scenarios.json")
        self.assertTrue(report["passed"], report["failures"])
        self.assertGreaterEqual(report["scenario_count"], 10)

    def test_eval_cli_is_machine_readable(self):
        result = subprocess.run(
            [sys.executable, "scripts/evaluate_planner.py", "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["passed_count"], payload["scenario_count"])

    def test_distribution_and_secret_validators_pass(self):
        commands = [
            (["scripts/validate_distribution.py", "--json"], True),
            (["scripts/security_scan.py", "--json"], True),
            (["scripts/sync_codex_plugin.py", "--check"], False),
        ]
        for argv, emits_json in commands:
            result = subprocess.run(
                [sys.executable, *argv],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            if emits_json:
                self.assertTrue(json.loads(result.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class PortabilityTests(unittest.TestCase):
    def test_cli_starts_and_plans_without_credentials(self):
        env = dict(os.environ, KIE_API_KEY="", KIE_MEDIA_HOME=tempfile.gettempdir())
        result = subprocess.run([sys.executable, "-m", "kie_media.cli", "agent", "plan",
                                 "An editorial image of a tree", "--no-preferences", "--json"],
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "ready")

    def test_lock_excludes_another_process_and_releases(self):
        from kie_media.agent import manifest_lock
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "run.json"
            script = "from kie_media.agent import manifest_lock; import sys\nwith manifest_lock(sys.argv[1]): print('acquired')"
            with manifest_lock(target):
                blocked = subprocess.run([sys.executable, "-c", script, str(target)], capture_output=True, text=True)
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn("already running", blocked.stderr)
            allowed = subprocess.run([sys.executable, "-c", script, str(target)], capture_output=True, text=True)
            self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_private_json_round_trip(self):
        from kie_media.catalog import _atomic_private_json
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            _atomic_private_json(path, {"version": 1})
            _atomic_private_json(path, {"version": 2})
            self.assertEqual(json.loads(path.read_text())["version"], 2)
            self.assertEqual([p.name for p in path.parent.iterdir()], ["cache.json"])

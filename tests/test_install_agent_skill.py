import tempfile
import unittest
from pathlib import Path

from scripts.install_agent_skill import InstallError, install_skill, resolve_destination


class AgentSkillInstallerTests(unittest.TestCase):
    def test_official_user_destinations(self):
        home = Path("/tmp/example-home").resolve()
        self.assertEqual(
            resolve_destination("claude", "user", home=home),
            home / ".claude" / "skills" / "kie-media",
        )
        self.assertEqual(
            resolve_destination("codex", "user", home=home),
            home / ".agents" / "skills" / "kie-media",
        )
        self.assertEqual(
            resolve_destination("hermes", "user", home=home),
            home / ".hermes" / "skills" / "media" / "kie-media",
        )

    def test_official_project_destinations(self):
        project = Path("/tmp/project").resolve()
        self.assertEqual(
            resolve_destination("claude", "project", project=project),
            project / ".claude" / "skills" / "kie-media",
        )
        self.assertEqual(
            resolve_destination("codex", "project", project=project),
            project / ".agents" / "skills" / "kie-media",
        )

    def test_installer_copies_complete_skill_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("---\nname: kie-media\ndescription: test\n---\nbody\n")
            (source / "references").mkdir()
            (source / "references" / "guide.md").write_text("guide\n")
            destination = root / "installed" / "kie-media"

            result = install_skill(source, destination)
            self.assertEqual(result, destination.resolve())
            self.assertEqual((result / "references" / "guide.md").read_text(), "guide\n")
            with self.assertRaises(InstallError):
                install_skill(source, destination)

            (source / "references" / "guide.md").write_text("updated\n")
            install_skill(source, destination, force=True)
            self.assertEqual((destination / "references" / "guide.md").read_text(), "updated\n")

    def test_dry_run_does_not_touch_destination(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("skill")
            destination = root / "target"
            result = install_skill(source, destination, dry_run=True)
            self.assertEqual(result, destination.resolve())
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()

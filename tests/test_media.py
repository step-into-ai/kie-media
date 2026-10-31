import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from kie_media.media import assemble_timeline, probe


class MediaProbeMetadataTests(unittest.TestCase):
    def test_probe_exposes_frame_rate_and_alpha_for_provider_constraints(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            media = Path(td) / "input.png"
            media.write_bytes(b"probe fixture")
            response = Mock(returncode=0, stdout=json.dumps({
                "format": {"format_name": "png_pipe"},
                "streams": [{"codec_type": "video", "width": 720, "height": 720,
                             "avg_frame_rate": "30000/1001", "pix_fmt": "rgba"}]}))
            with patch("kie_media.media._tool", return_value="ffprobe"), patch("kie_media.media.subprocess.run", return_value=response):
                info = probe(media)
            self.assertAlmostEqual(info["fps"], 29.97002997)
            self.assertTrue(info["has_alpha"])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/ffprobe required")
class MediaIntegrationTests(unittest.TestCase):
    def test_real_assembly_with_narration_music_and_captions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            video, voice, music = root / "clip.mp4", root / "voice.wav", root / "music.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-c:v", "libx264", str(video)], check=True)
            for target, frequency in [(voice, 440), (music, 220)]:
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=1.4", str(target)], check=True)
            from kie_media.projects import create_project, import_asset, project_plan, render_project
            project = root / "project.json"
            create_project(project, "Fixture", shots=1)
            with self.assertRaises(ValueError):
                import_asset(project, "scene-1.image", video)
            import_asset(project, "scene-1.video", video)
            plan = project_plan(project)
            self.assertEqual(plan["stages"][0]["state"], "not_required_imported_video")
            self.assertEqual(plan["pending_jobs"], 0)
            with self.assertRaisesRegex(ValueError, "Review required"):
                render_project(project)
            result = assemble_timeline([
                {"video": str(video), "voice": str(voice), "duration": 1, "narration": "First scene."},
                {"video": str(video), "duration": 1, "narration": "Second scene."},
            ], root / "result.mp4", aspect_ratio="9:16", music=str(music), captions=True)
            data = probe(Path(result["file"]))
            self.assertGreater(data["duration"], 2.3)
            self.assertEqual((data["width"], data["height"]), (720, 1280))
            self.assertTrue(data["audio"])
            self.assertTrue(Path(result["subtitles"]).is_file())

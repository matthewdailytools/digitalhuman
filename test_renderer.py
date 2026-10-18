import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cache_pipeline import cache_key
import render_settings
from renderer import render, validate_video


class RendererTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((Path(__file__).parent / "configs/head-draft.json").read_text("utf-8"))
        self.probe = {"streams": [{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p",
                       "width": 1280, "height": 720, "r_frame_rate": "24/1", "nb_read_frames": "72"}],
                      "format": {"duration": "3.0"}}

    def test_rejects_unsupported_or_unencodable_settings(self):
        for section, name, value in [("quality", "width", 1279), ("quality", "hair", "strands"),
                                     ("performance", "text", "not synthesized"),
                                     ("performance", "expression", "angry")]:
            config = copy.deepcopy(self.config)
            config[section][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                render_settings.validate(config)
        self.config["quality"]["unimplemented"] = True
        with self.assertRaises(ValueError):
            render_settings.validate(self.config)

    def test_incomplete_or_wrong_video_cannot_pass(self):
        validate_video(self.probe, self.config, False)
        for name, value in [("nb_read_frames", "71"), ("r_frame_rate", "30/1"), ("width", 640)]:
            data = copy.deepcopy(self.probe)
            data["streams"][0][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_video(data, self.config, False)
        with self.assertRaises(ValueError):
            validate_video(self.probe, self.config, True)

    def test_audio_must_cover_full_timeline(self):
        self.probe["streams"].append({"codec_type": "audio", "codec_name": "aac", "duration": "3.0"})
        validate_video(self.probe, self.config, True)
        self.probe["streams"][1]["duration"] = "0.5"
        with self.assertRaises(ValueError):
            validate_video(self.probe, self.config, True)

    def test_source_edits_invalidate_cache_without_manual_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            tool = Path(directory) / "tool.exe"
            tool.write_bytes(b"tool")
            with patch.object(render_settings, "tool_paths", return_value={n: str(tool) for n in ("blender", "ffmpeg", "ffprobe")}):
                before = render_settings.resolve(self.config)
                original = render_settings.sha256
                with patch.object(render_settings, "sha256", side_effect=lambda p: "changed" if Path(p).name == "create_head_scene.py" else original(p)):
                    after = render_settings.resolve(self.config)
        self.assertNotEqual(cache_key(before), cache_key(after))

    def test_stale_snapshot_rejected_before_renderer_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps(self.config), encoding="utf-8")
            changed = copy.deepcopy(self.config)
            changed["generator"]["resolved_signature"] = "changed"
            with patch("renderer.resolve", return_value=changed), patch("renderer.subprocess.run") as launch:
                with self.assertRaises(ValueError):
                    render(config, Path(directory) / "output.mp4")
                launch.assert_not_called()

    def test_windows_line_endings_do_not_invalidate_identical_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "script.py"
            path.write_bytes(b"print('same')\n")
            before = render_settings.sha256(path)
            path.write_bytes(b"print('same')\r\n")
            self.assertEqual(before, render_settings.sha256(path))


if __name__ == "__main__":
    unittest.main()

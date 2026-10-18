import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch

from speech import binary_hash, load_bundle, validate_bundle, viseme_weights
from cache_pipeline import cache_key
import render_settings


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.data = {"schema_version": 1, "text": "test", "duration_seconds": 1.0,
                     "audio_file": "audio.wav", "audio_sha256": "0" * 64,
                     "events": [{"start": 0.2, "end": 0.6, "viseme": "A", "strength": 1.0}]}

    def test_rejects_bad_alignment_and_weights(self):
        for field, value in [("start", -1), ("end", 1.1), ("end", math.nan),
                             ("viseme", "UNKNOWN"), ("strength", 1.1)]:
            data = copy.deepcopy(self.data)
            data["events"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_bundle(data)
        self.data["events"].append({"start": 0.5, "end": 0.8, "viseme": "O"})
        with self.assertRaises(ValueError):
            validate_bundle(self.data)

    def test_gaps_and_end_are_closed(self):
        for time in (0, 0.15, 0.6, 0.9, 2.0):
            self.assertEqual(sum(viseme_weights(time, self.data["events"]).values()), 0)
        self.assertEqual(viseme_weights(0.4, self.data["events"])["A"], 1)

    def test_adjacent_events_crossfade_without_weight_overshoot(self):
        events = [{"start": 0, "end": 0.5, "viseme": "A"},
                  {"start": 0.5, "end": 1.0, "viseme": "O"}]
        left = viseme_weights(0.5 - 1e-6, events)
        right = viseme_weights(0.5 + 1e-6, events)
        self.assertAlmostEqual(left["A"], right["A"], places=5)
        for i in range(1001):
            values = viseme_weights(i / 1000, events)
            self.assertTrue(all(0 <= v <= 1 for v in values.values()))
            self.assertLessEqual(sum(values.values()), 1.000001)

    def test_explicit_rest_closes_mouth(self):
        events = [{"start": 0, "end": 0.5, "viseme": "A"},
                  {"start": 0.5, "end": 1.0, "viseme": "REST"}]
        self.assertLess(sum(viseme_weights(0.499, events).values()), 0.002)
        self.assertEqual(sum(viseme_weights(0.51, events).values()), 0)

    def test_audio_content_and_duration_must_match_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            with wave.open(str(path / "audio.wav"), "wb") as audio:
                audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                audio.writeframes(b"\0\0" * 8000)
            self.data["audio_sha256"] = binary_hash(path / "audio.wav")
            bundle = path / "tts.json"
            bundle.write_text(json.dumps(self.data), encoding="utf-8")
            load_bundle(bundle)
            self.data["duration_seconds"] = 0.9
            bundle.write_text(json.dumps(self.data), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_bundle(bundle)
            self.data["duration_seconds"] = 1
            self.data["audio_sha256"] = "0" * 64
            bundle.write_text(json.dumps(self.data), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_bundle(bundle)

    def test_changed_timing_invalidates_cache_even_with_identical_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            audio = path / "audio.wav"
            with wave.open(str(audio), "wb") as stream:
                stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                stream.writeframes(b"\0\0" * 8000)
            bundle = path / "tts.json"
            self.data["audio_sha256"] = binary_hash(audio)
            bundle.write_text(json.dumps(self.data), encoding="utf-8")
            config = json.loads((Path(__file__).parent / "configs/head-draft.json").read_text("utf-8"))
            config["performance"].update(text="test", tts_file=str(bundle))
            tool = path / "tool.exe"
            tool.write_bytes(b"tool")
            with patch.object(render_settings, "tool_paths", return_value={n: str(tool) for n in ("blender", "ffmpeg", "ffprobe")}):
                before = render_settings.resolve(config)
                self.data["events"][0]["viseme"] = "O"
                bundle.write_text(json.dumps(self.data), encoding="utf-8")
                after = render_settings.resolve(config)
                self.assertNotEqual(cache_key(before), cache_key(after))
                self.assertEqual(before["performance"]["audio_sha256"], after["performance"]["audio_sha256"])


if __name__ == "__main__":
    unittest.main()

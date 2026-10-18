import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

from cache_pipeline import cache_key, generate, lookup, main, publish, read_config


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = read_config(Path(__file__).with_name("prototype.json"))
        # Opaque bytes test cache integrity only, not video decoding or visual quality.
        self.video = self.root / "input.mp4"
        self.video.write_bytes(b"cache-integrity-fixture")

    def test_settings_invalidate_cache(self):
        for section, field in [("quality", "hair"), ("scene", "camera"),
                               ("character", "revision"), ("performance", "text"),
                               ("generator", "revision")]:
            modified = copy.deepcopy(self.config)
            modified[section][field] = "changed"
            self.assertNotEqual(cache_key(self.config), cache_key(modified))
        reordered = dict(reversed(list(self.config.items())))
        self.assertEqual(cache_key(self.config), cache_key(reordered))

    def test_publish_replay_and_corruption(self):
        video = publish(self.root / "cache", self.config, self.video)
        self.assertEqual(lookup(self.root / "cache", self.config), video)
        video.write_bytes(b"damaged")
        self.assertIsNone(lookup(self.root / "cache", self.config))

    def test_failed_generation_preserves_existing(self):
        root = self.root / "cache"
        original = publish(root, self.config, self.video)
        with self.assertRaises(subprocess.CalledProcessError):
            generate(root, self.config,
                     [sys.executable, "-c", "import sys; sys.exit(1)", "{output}"])
        self.assertEqual(lookup(root, self.config), original)

    def test_second_prepare_never_calls_generator(self):
        root = self.root / "cache"
        publish(root, self.config, self.video)
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(self.config), encoding="utf-8")
        result = main(["prepare", "--cache", str(root), "--config", str(config_path),
                       "--command-file", str(self.root / "does-not-exist.json")])
        self.assertEqual(result, 0)
        self.assertEqual(main(["play", "--dry-run", "--cache", str(root),
                               "--config", str(config_path)]), 0)

    def test_external_generator_writes_output(self):
        command = [sys.executable, "-c",
                   "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'generated')",
                   "{output}"]
        video = generate(self.root / "cache", self.config, command)
        self.assertEqual(video.read_bytes(), b"generated")

    def test_manifest_cannot_reference_outside_cache(self):
        root = self.root / "cache"
        video = publish(root, self.config, self.video)
        manifest_path = video.parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text("utf-8"))
        manifest["media"] = "../../input.mp4"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertIsNone(lookup(root, self.config))


if __name__ == "__main__":
    unittest.main()

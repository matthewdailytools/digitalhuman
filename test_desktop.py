import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from desktop_controller import Jobs, BusyError, selection, cache_status
from desktop_console import Player
from cache_pipeline import publish, read_config


class DesktopTests(unittest.TestCase):
    def test_refuses_unknown_presets_and_fields(self):
        with self.assertRaises(ValueError):
            selection({"preset": "../../local-tools.json"})
        with self.assertRaises(ValueError):
            selection({"preset": "head-draft", "settings": {"command": "anything"}})

    def test_only_one_task_runs_at_once(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = Jobs(directory)
            release, done = threading.Event(), threading.Event()
            def wait(*args):
                release.wait(3)
                done.set()
            with patch.object(jobs, "_run", side_effect=wait):
                jobs.start("tests")
                with self.assertRaises(BusyError):
                    jobs.start("mock-tts")
                release.set()
                self.assertTrue(done.wait(3))

    def test_missing_cache_never_appears_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            config = read_config(Path(__file__).parent / "prototype.json")
            config["performance"]["frames"] = 72
            with patch("desktop_controller.CACHE", Path(directory)):
                self.assertFalse(cache_status(config)["hit"])

    def test_cache_returns_local_file_not_network_url(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            config = read_config(Path(__file__).parent / "prototype.json")
            config["performance"]["frames"] = 72
            source = folder / "input.mp4"
            source.write_bytes(b"opaque cache fixture")
            publish(folder / "cache", config, source)
            with patch("desktop_controller.CACHE", folder / "cache"):
                result = cache_status(config)
            self.assertTrue(result["hit"])
            self.assertTrue(Path(result["media_path"]).is_file())
            self.assertNotIn("media_url", result)

    def test_stop_only_terminates_the_owned_player(self):
        player = Player()
        owned = Mock()
        owned.poll.return_value = None
        player.process = owned
        player.stop()
        owned.terminate.assert_called_once()
        owned.wait.assert_called_once_with(timeout=3)
        self.assertIsNone(player.process)

    def test_finished_player_is_not_terminated_again(self):
        player = Player()
        owned = Mock()
        owned.poll.return_value = 0
        player.process = owned
        player.stop()
        owned.terminate.assert_not_called()


if __name__ == "__main__":
    unittest.main()

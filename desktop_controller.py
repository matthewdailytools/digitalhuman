"""Native desktop test controller: serial jobs and local cache, no HTTP server."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from cache_pipeline import cache_key, lookup
from render_settings import PROJECT, resolve
from speech import load_bundle

WORK = PROJECT / "work/desktop"
CACHE = PROJECT / ".cache/digitalhuman"
PRESETS = {"mock-tts": PROJECT / "work/mock-tts/render-config.json", "head-draft": PROJECT / "configs/head-draft.json"}

def presets():
    result = []
    for key, path in PRESETS.items():
        if path.is_file():
            config = json.loads(path.read_text("utf-8-sig"))
            result.append({"id": key, "name": "模拟中文 TTS / 嘴型" if key == "mock-tts" else "半身 / 待机动画",
                           "config": config})
    return result


def selection(data):
    if set(data) - {"preset", "settings"}:
        raise ValueError("不支持的请求字段")
    if data.get("preset") not in PRESETS or not PRESETS[data["preset"]].is_file():
        raise ValueError("请选择已存在的测试配置")
    config = json.loads(PRESETS[data["preset"]].read_text("utf-8-sig"))
    settings = data.get("settings", {})
    if not isinstance(settings, dict) or set(settings) - {"width", "height", "fps", "samples", "hair", "camera", "frames"}:
        raise ValueError("不支持的测试参数")
    for key in ("width", "height", "fps", "samples", "hair"):
        if key in settings:
            config["quality"][key] = settings[key]
    if "camera" in settings:
        config["scene"]["camera"] = settings["camera"]
    if "frames" in settings:
        config["performance"]["frames"] = settings["frames"]
    return resolve(config)


def cache_status(config):
    media = lookup(CACHE, config)
    summary = {"hit": bool(media), "key": cache_key(config), "media_path": None,
               "width": config["quality"]["width"], "height": config["quality"]["height"],
               "fps": config["quality"]["fps"], "frames": config["performance"]["frames"],
               "duration": config["performance"]["frames"] / config["quality"]["fps"],
               "text": config["performance"]["text"], "speech": None}
    if media:
        summary["media_path"] = str(media.resolve())
        summary["bytes"] = media.stat().st_size
    if config["performance"].get("tts_file"):
        bundle = load_bundle(config["performance"]["tts_file"])
        summary["speech"] = {"source": bundle.get("source"), "alignment": bundle.get("alignment"),
                             "events": bundle["events"]}
    return summary


class BusyError(ValueError):
    pass


class Jobs:
    def __init__(self, work=WORK):
        self.work = Path(work)
        self.lock = threading.RLock()
        self.current = None

    def start(self, kind, config=None, force=False):
        if kind not in ("render", "mock-tts", "tests"):
            raise ValueError("未知任务")
        if kind == "render" and not isinstance(config, dict):
            raise ValueError("生成任务需要配置")
        with self.lock:
            if self.current and self.current["state"] == "running":
                raise BusyError("已有任务运行，请等待完成")
            directory = self.work / uuid.uuid4().hex
            directory.mkdir(parents=True)
            if kind == "render":
                path = directory / "config.json"
                path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
                command = [sys.executable, str(PROJECT / "cache_pipeline.py"), "prepare", "--config", str(path),
                           "--command-file", str(PROJECT / "renderer-command.json")]
                if force:
                    command.append("--force")
            elif kind == "mock-tts":
                command = [sys.executable, str(PROJECT / "tools/mock_tts.py")]
            else:
                command = [sys.executable, "-m", "unittest", "-v"]
            job = {"id": directory.name, "kind": kind, "state": "running", "stage": "starting",
                   "logs": [], "started": time.time(), "progress": 0, "frames_done": 0,
                   "config": config, "render_dir": None, "summary": None, "elapsed": 0}
            self.current = job
            threading.Thread(target=self._run, args=(job, command, directory), daemon=True).start()
            return self.snapshot()

    def _run(self, job, command, directory):
        try:
            env = os.environ.copy()
            env.update(PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            with (directory / "task.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, cwd=PROJECT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, encoding="utf-8", errors="replace", env=env, shell=False,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    with self.lock:
                        job["logs"].append(line.rstrip())
                        job["logs"] = job["logs"][-200:]
                        for stage in ("blender", "encode", "decode"):
                            if line.startswith(stage + ": "):
                                job["stage"] = stage
                                if stage == "blender":
                                    candidate = Path(line.split(": ", 1)[1].strip()).resolve()
                                    if candidate.is_relative_to((PROJECT / "work/render-jobs").resolve()):
                                        job["render_dir"] = candidate
                        if "CACHE HIT" in line:
                            job["stage"] = "cache-hit"
                code = process.wait()
            with self.lock:
                job["state"] = "succeeded" if code == 0 else "failed"
                job["exit_code"] = code
                job["elapsed"] = round(time.time() - job["started"], 2)
                if code == 0:
                    job["progress"] = 100
                    if job["config"]:
                        job["summary"] = cache_status(job["config"])
        except Exception as error:
            with self.lock:
                job["state"] = "failed"
                job["logs"].append(str(error))
                job["elapsed"] = round(time.time() - job["started"], 2)

    def snapshot(self):
        with self.lock:
            if not self.current:
                return None
            job = self.current
            if job["state"] == "running":
                job["elapsed"] = round(time.time() - job["started"], 1)
                if job["render_dir"] and job["config"]:
                    done = len(list((job["render_dir"] / "frames").glob("frame_*.png")))
                    job["frames_done"] = done
                    job["progress"] = min(90, round(90 * done / job["config"]["performance"]["frames"]))
                if job["stage"] in ("encode", "decode"):
                    job["progress"] = 95 if job["stage"] == "encode" else 98
            return copy.deepcopy({key: value for key, value in job.items() if key not in ("config", "render_dir")})


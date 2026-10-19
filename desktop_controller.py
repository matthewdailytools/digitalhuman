"""Native desktop test controller: serial jobs and local cache, no HTTP server."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
import threading
import time
import uuid
from cache_pipeline import cache_key, lookup
from render_settings import PROJECT, resolve
from speech import load_bundle

WORK = PROJECT / "work/desktop"
CACHE = PROJECT / ".cache/digitalhuman"
PRESETS = {"mock-tts": PROJECT / "work/mock-tts/render-config.json", "head-draft": PROJECT / "configs/head-draft.json", "custom": PROJECT / "work/text/render-config.json"}
PRESETS['micro'] = PROJECT/'work/micro/render-config.json'

def worker_python():
    # GUI pythonw can lose stdout in nested workers; console python stays hidden via Popen flags.
    executable=Path(sys.executable)
    console=executable.with_name('python.exe')
    return str(console) if executable.name.lower()=='pythonw.exe' and console.is_file() else sys.executable


def refresh_acceptance_presets():
    names = [f'speech-{i:02d}' for i in range(1,11)] + ['expression-'+e for e in ('neutral-with-blink','smile','curious','surprised')] + ['hair-'+h for h in ('none','static','sway')] + ['preview-combined']
    for name in names:
        path = PROJECT/'work/acceptance'/(name+'.json')
        if path.is_file():
            PRESETS['acceptance-'+name] = path


def presets():
    refresh_acceptance_presets()
    result = []
    for key, path in PRESETS.items():
        if path.is_file():
            config = json.loads(path.read_text("utf-8-sig"))
            result.append({"id": key, "name": "模拟中文 TTS / 嘴型" if key == "mock-tts" else ("自定义台词 / AI 回复" if key == "custom" else ("验收 / "+key.removeprefix('acceptance-') if key.startswith('acceptance-') else "半身 / 待机动画")),
                           "config": config})
            if key == 'micro':
                result[-1]['name'] = '五项控制 / 最近结果'
    return result


def selection(data):
    refresh_acceptance_presets()
    if set(data) - {"preset", "settings"}:
        raise ValueError("不支持的请求字段")
    if data.get("preset") not in PRESETS or not PRESETS[data["preset"]].is_file():
        raise ValueError("请选择已存在的测试配置")
    config = json.loads(PRESETS[data["preset"]].read_text("utf-8-sig"))
    settings = data.get("settings", {})
    if not isinstance(settings, dict) or set(settings) - {"width", "height", "fps", "samples", "hair", "camera", "frames", "expression", "motion", "strength", "gaze", "enter", "leave", "profile"}:
        raise ValueError("不支持的测试参数")
    for key in ("width", "height", "fps", "samples", "hair"):
        if key in settings:
            config["quality"][key] = settings[key]
    if "camera" in settings:
        config["scene"]["camera"] = settings["camera"]
    if "profile" in settings:
        from quality_profiles import apply_profile
        config = apply_profile(config, settings["profile"])
        # Individual visible controls override preset defaults and remain part of the hash.
        for name in ("width", "height", "fps", "samples", "hair"):
            if name in settings:
                config["quality"][name] = settings[name]
    for name in ("frames", "expression", "strength", "gaze", "enter", "leave"):
        if name in settings:
            defaults = {'strength':0.6, 'gaze':'camera', 'enter':0.25, 'leave':0.25}
            if name not in config['performance'] and name in defaults and settings[name] == defaults[name]:
                continue
            config["performance"][name] = settings[name]
    if "motion" in settings:
        config["performance"]["motion_revision"] = settings["motion"]
    return resolve(config)


def cache_status(config):
    media = lookup(CACHE, config)
    summary = {"hit": bool(media), "key": cache_key(config), "media_path": None,
               "width": config["quality"]["width"], "height": config["quality"]["height"],
               "fps": config["quality"]["fps"], "frames": config["performance"]["frames"],
               "duration": config["performance"]["frames"] / config["quality"]["fps"],
               "text": config["performance"]["text"], "speech": None,
               "micro_control": config['performance'].get('micro_control')}
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

    def start(self, kind, config=None, force=False, request=None):
        if kind not in ("render", "mock-tts", "tests", "text", "reel", "acceptance", "answer", "micro"):
            raise ValueError("未知任务")
        if kind == "render" and not isinstance(config, dict):
            raise ValueError("生成任务需要配置")
        with self.lock:
            if self.current and self.current["state"] == "running":
                raise BusyError("已有任务运行，请等待完成")
            directory = self.work / uuid.uuid4().hex
            directory.mkdir(parents=True)
            python = worker_python()
            response_dir = directory / 'response'
            response_dir.mkdir()
            if kind == "render":
                path = directory / "config.json"
                path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
                command = [python, str(PROJECT / "cache_pipeline.py"), "prepare", "--config", str(path),
                           "--command-file", str(PROJECT / "renderer-command.json")]
                if force:
                    command.append("--force")
            elif kind in ("text", "answer", "micro"):
                path = directory / "request.json"
                path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
                script = {'answer': 'conversation.py', 'text': 'text_pipeline.py', 'micro': 'micro_pipeline.py'}[kind]
                command = [python, str(PROJECT / script), "--request", str(path), "--output", str(response_dir)]
            elif kind == "reel":
                if not config or not config["performance"].get("tts_file"):
                    raise ValueError("请先选择含语音的配置")
                path = directory / "config.json"
                path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
                command = [python, str(PROJECT / "playback.py"), "--config", str(path), "--output", str(response_dir / "reel.json"), "--profile", config["quality"]["profile"]]
            elif kind == "acceptance":
                command = [python, str(PROJECT / "tools/acceptance.py")]
            elif kind == "mock-tts":
                command = [python, str(PROJECT / "tools/mock_tts.py")]
            else:
                command = [python, "-m", "unittest", "-v"]
            job = {"id": directory.name, "kind": kind, "state": "running", "stage": "starting",
                   "logs": [], "started": time.time(), "progress": 0, "frames_done": 0,
                   "config": config, "render_dir": None, "output_dir": str(response_dir), "summary": None, "elapsed": 0}
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
                                        if job['kind'] in ('answer', 'micro'):
                                            job['config'] = json.loads((candidate/'config.json').read_text('utf-8'))
                        if "CACHE HIT" in line:
                            job["stage"] = "cache-hit"
                code = process.wait()
            if code == 0 and job['kind'] in ('text','answer','reel','micro'):
                # UI consumes its own task output; these atomic pointers only select the latest preset.
                names = ('reel.json',) if job['kind'] == 'reel' else ('render-config.json','result.json','answer.json','plan.json')
                target = PROJECT / {'reel':'work/desktop','micro':'work/micro'}.get(job['kind'], 'work/text')
                target.mkdir(parents=True,exist_ok=True)
                for name in names:
                    source=Path(job['output_dir'])/name
                    if source.is_file():
                        temporary=target/(name+'.'+job['id']+'.tmp')
                        shutil.copyfile(source,temporary)
                        os.replace(temporary,target/name)
            with self.lock:
                job["state"] = "succeeded" if code == 0 else "failed"
                job["exit_code"] = code
                job["elapsed"] = round(time.time() - job["started"], 2)
                if code == 0:
                    job["progress"] = 100
                    if job["config"] and job["kind"] == "render":
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


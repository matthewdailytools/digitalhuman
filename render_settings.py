"""Validated contract and cache identity for the bundled offline renderer."""
import copy
import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
GENERATOR_ID = "blender-offline-v1"


def tool_paths():
    paths = json.loads((PROJECT / "local-tools.json").read_text("utf-8-sig"))
    for name in ("blender", "ffmpeg", "ffprobe"):
        path = Path(paths[name]).resolve()
        if not path.is_file():
            raise ValueError(f"Tool missing: {name}: {path}")
        paths[name] = str(path)
    return paths


def sha256(path):
    path = Path(path)
    if path.suffix == ".py":
        # Git may rewrite LF/CRLF on Windows checkout; identical code keeps its cache identity.
        content = path.read_text(encoding="utf-8-sig")
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate(config):
    expected = {
        "character": {"id": "procedural-head", "revision": "v1"},
        "scene": {"revision": "v1", "lighting": "three-area-lights"},
    }
    allowed = {
        "schema_version": None, "character": set(expected["character"]),
        "scene": set(expected["scene"]) | {"camera"},
        "quality": {"profile", "width", "height", "fps", "samples", "hair", "skin", "body"},
        "performance": {"text", "expression", "motion_revision", "frames", "audio_file", "audio_sha256", "tts_file", "tts_sha256"},
        "generator": {"id", "revision", "resolved_signature"},
    }
    unknown = set(config) - set(allowed)
    if unknown:
        raise ValueError(f"Unsupported sections: {sorted(unknown)}")
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported schema_version")
    for section, keys in allowed.items():
        if keys is not None:
            value = config.get(section)
            if not isinstance(value, dict):
                raise ValueError(f"Missing section: {section}")
            if set(value) - keys:
                raise ValueError(f"Unsupported {section} fields: {sorted(set(value) - keys)}")
    for section, values in expected.items():
        for name, value in values.items():
            if config[section].get(name) != value:
                raise ValueError(f"Unsupported {section}.{name}; currently requires {value}")
    quality, performance = config["quality"], config["performance"]
    if config["scene"].get("camera") not in ("fixed-half-body", "head-closeup"):
        raise ValueError("Unsupported camera")
    for name, lo, hi in (("width", 64, 1920), ("height", 64, 1080), ("fps", 1, 60), ("samples", 1, 64)):
        value = quality.get(name)
        if type(value) is not int or not lo <= value <= hi:
            raise ValueError(f"quality.{name} must be an integer from {lo} to {hi}")
    if quality["width"] % 2 or quality["height"] % 2:
        raise ValueError("H.264 dimensions must be even")
    if quality.get("profile") != "draft" or quality.get("skin") != "simple" or quality.get("body") != "bust":
        raise ValueError("Only draft profile, simple skin and bust body are implemented")
    if quality.get("hair") not in ("none", "static"):
        raise ValueError("hair must be none or static")
    frames = performance.get("frames")
    if type(frames) is not int or not 2 <= frames <= quality["fps"] * 30:
        raise ValueError("frames must describe 2 frames to 30 seconds")
    if not isinstance(performance.get("text"), str) or (performance["text"] and not performance.get("tts_file")):
        raise ValueError("Nonempty text requires a TTS timing bundle")
    if performance.get("expression") != "neutral-with-blink" or performance.get("motion_revision") != "idle-v1":
        raise ValueError("Only neutral-with-blink expression and idle-v1 motion are implemented")
    if config["generator"].get("id") != GENERATOR_ID or config["generator"].get("revision") != "v1":
        raise ValueError("Unsupported renderer identity")


def resolve(config):
    config = copy.deepcopy(config)
    validate(config)
    performance = config["performance"]
    if performance.get("tts_file"):
        from speech import load_bundle
        tts_path = Path(performance["tts_file"])
        if not tts_path.is_absolute():
            tts_path = PROJECT / tts_path
        bundle = load_bundle(tts_path)
        if performance["text"] != bundle["text"]:
            raise ValueError("Configured text does not match TTS bundle")
        if bundle["duration_seconds"] > performance["frames"] / config["quality"]["fps"]:
            raise ValueError("TTS timing exceeds the configured frame timeline")
        if performance.get("audio_file") and Path(performance["audio_file"]).resolve() != Path(bundle["audio_file"]):
            raise ValueError("Conflicting audio_file and TTS audio")
        performance["tts_file"] = str(tts_path.resolve())
        performance["tts_sha256"] = sha256(tts_path)
        performance["audio_file"] = bundle["audio_file"]
    elif performance.get("tts_sha256"):
        raise ValueError("tts_sha256 requires tts_file")
    if performance.get("audio_file"):
        path = Path(performance["audio_file"])
        if not path.is_absolute():
            path = PROJECT / path
        if not path.is_file():
            raise ValueError(f"Audio file missing: {path}")
        performance["audio_file"] = str(path.resolve())
        performance["audio_sha256"] = sha256(path)
    elif performance.get("audio_sha256"):
        raise ValueError("audio_sha256 requires audio_file")
    tools = tool_paths()
    identity = {
        "scripts": {name: sha256(PROJECT / name) for name in
                    ("renderer.py", "render_settings.py", "speech.py", "tools/create_head_scene.py")},
        "tools": {name: {"path": tools[name], "size": Path(tools[name]).stat().st_size,
                         "mtime_ns": Path(tools[name]).stat().st_mtime_ns}
                  for name in ("blender", "ffmpeg", "ffprobe")},
    }
    config["generator"]["resolved_signature"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()
    return config

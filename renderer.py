"""Blender -> PNG sequence -> H.264 -> validated output. No external AI calls."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from render_settings import PROJECT, resolve, sha256, tool_paths
from speech import load_bundle


def probe(executable, path, count_frames=False):
    command = [executable, "-v", "error"]
    if count_frames:
        command.append("-count_frames")
    result = subprocess.run(command + ["-show_streams", "-show_format", "-of", "json", str(path)],
                            capture_output=True, text=True, check=True, timeout=120)
    return json.loads(result.stdout)


def validate_video(data, config, expect_audio):
    quality, performance = config["quality"], config["performance"]
    videos = [s for s in data.get("streams", []) if s["codec_type"] == "video"]
    audios = [s for s in data.get("streams", []) if s["codec_type"] == "audio"]
    if len(videos) != 1 or len(audios) != int(expect_audio):
        raise ValueError("Unexpected video/audio stream count")
    video = videos[0]
    if (video["codec_name"] != "h264" or video["pix_fmt"] != "yuv420p"
            or video["width"] != quality["width"] or video["height"] != quality["height"]
            or Fraction(video["r_frame_rate"]) != quality["fps"]
            or int(video["nb_read_frames"]) != performance["frames"]):
        raise ValueError("Encoded video does not match requested dimensions, fps, frames or codec")
    expected_duration = performance["frames"] / quality["fps"]
    if abs(float(data["format"]["duration"]) - expected_duration) > 1 / quality["fps"] + 0.01:
        raise ValueError("Encoded duration does not match requested timeline")
    if audios and audios[0]["codec_name"] != "aac":
        raise ValueError("Expected AAC audio")
    if audios and abs(float(audios[0]["duration"]) - expected_duration) > 0.06:
        raise ValueError("Audio track does not cover the configured timeline")


def render(config_path, output):
    snapshot = json.loads(Path(config_path).read_text("utf-8-sig"))
    config = resolve(snapshot)
    # Reject stale snapshots instead of publishing changed assets under an old key.
    if snapshot != config:
        raise ValueError("Configuration snapshot is unresolved or assets/tools changed; run cache prepare again")
    tools = tool_paths()
    quality, performance = config["quality"], config["performance"]
    job = PROJECT / "work" / "render-jobs" / uuid.uuid4().hex
    job.mkdir(parents=True)
    (job / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"job": str(job), "success": False, "stages": {}, "has_audio": False}

    def run_stage(name, command, timeout):
        print(f"{name}: {job}", flush=True)
        started = time.perf_counter()
        with (job / (name + ".log")).open("w", encoding="utf-8") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=timeout, shell=False, cwd=PROJECT)
        report["stages"][name] = round(time.perf_counter() - started, 3)

    try:
        audio = None
        if performance.get("audio_file"):
            source = Path(performance["audio_file"])
            audio = job / ("audio" + source.suffix.lower())
            shutil.copyfile(source, audio)
            if sha256(audio) != performance["audio_sha256"]:
                raise ValueError("Audio changed after cache configuration was resolved")
            audio_data = probe(tools["ffprobe"], audio)
            if not any(s["codec_type"] == "audio" for s in audio_data.get("streams", [])):
                raise ValueError("Input has no audio stream")
            duration = float(audio_data["format"]["duration"])
            if duration <= 0 or duration > performance["frames"] / quality["fps"] + 0.01:
                raise ValueError("Audio must fit the configured frame timeline; increase frames")
            report["has_audio"] = True
        speech_args = []
        if performance.get("tts_file"):
            if sha256(performance["tts_file"]) != performance["tts_sha256"]:
                raise ValueError("TTS bundle changed after cache configuration was resolved")
            bundle = load_bundle(performance["tts_file"])
            bundle["audio_file"] = str(audio)
            speech_path = job / "tts.json"
            speech_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            speech_args = ["--tts-file", str(speech_path)]
            report["speech_source"] = bundle.get("source", "unspecified")
            report["alignment"] = bundle.get("alignment", "unspecified")
        frames = job / "frames"
        run_stage("blender", [tools["blender"], "--background", "--factory-startup",
                  "--python-exit-code", "1", "--python", str(PROJECT / "tools/create_head_scene.py"),
                  "--", "--output", str(frames), "--render", "animation",
                  "--width", str(quality["width"]), "--height", str(quality["height"]),
                  "--fps", str(quality["fps"]), "--samples", str(quality["samples"]),
                  "--frames", str(performance["frames"]), "--hair", quality["hair"],
                  "--camera", config["scene"]["camera"], "--skin", quality["skin"],
                  "--expression", performance["expression"], "--motion", performance["motion_revision"],
                  "--strength", str(performance.get("strength", 0.6)),
                  "--enter", str(performance.get("enter", 0.25)), "--leave", str(performance.get("leave", 0.25)),
                  "--gaze", performance.get("gaze", "camera"), *speech_args], 1800)
        for frame in range(1, performance["frames"] + 1):
            image = frames / f"frame_{frame:04d}.png"
            if not image.is_file() or image.stat().st_size == 0:
                raise ValueError(f"Missing or empty frame: {frame}")
        encoded = job / "video.mp4"
        command = [tools["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y",
                   "-framerate", str(quality["fps"]), "-start_number", "1",
                   "-i", str(frames / "frame_%04d.png")]
        if audio:
            command += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-af", "apad",
                        "-c:a", "aac", "-t", str(performance["frames"] / quality["fps"])]
        else:
            command += ["-an"]
        command += ["-frames:v", str(performance["frames"]), "-c:v", "libx264", "-threads", "2",
                    "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(encoded)]
        run_stage("encode", command, 300)
        data = probe(tools["ffprobe"], encoded, count_frames=True)
        validate_video(data, config, bool(audio))
        (job / "video-probe.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        run_stage("decode", [tools["ffmpeg"], "-v", "error", "-xerror", "-i", str(encoded), "-f", "null", "-"], 300)
        if resolve(config) != config:
            raise ValueError("Assets/tools changed during generation; refusing to publish stale output")
        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(encoded, output)
        report.update(success=True, output=str(output), video_sha256=sha256(output))
        print(f"RENDER VALIDATED: {encoded}", flush=True)
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (job / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        render(args.config, args.output)
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"RENDER FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

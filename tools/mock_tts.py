"""Produce a repeatable test API payload from Windows speech; no network or AI model."""
import argparse
from array import array
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import wave

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
from speech import binary_hash, load_bundle, MOUTH_SHAPES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", default=str(PROJECT / "fixtures/mock-tts-request.json"))
    parser.add_argument("--output", default=str(PROJECT / "work/mock-tts"))
    args = parser.parse_args()
    request_path = Path(args.request).resolve()
    request = json.loads(request_path.read_text("utf-8-sig"))
    for segment in request["segments"]:
        if not segment["visemes"] or any(v not in MOUTH_SHAPES for v in segment["visemes"]):
            raise ValueError("Fixture contains an unsupported viseme")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    raw = output / "raw"
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise RuntimeError("Windows PowerShell is required for mock SAPI voice")
    subprocess.run([shell, "-NoProfile", "-File", str(PROJECT / "tools/mock_tts_voice.ps1"),
                    "-Request", str(request_path), "-Output", str(raw)], check=True, timeout=120)
    rate = 22050
    audio = array("h", [0] * round(rate * 0.25))
    events, segments, pauses = [], [], [(0, len(audio) / rate)]
    for index, segment in enumerate(request["segments"]):
        with wave.open(str(raw / f"syllable_{index:02d}.wav"), "rb") as stream:
            if (stream.getframerate(), stream.getsampwidth(), stream.getnchannels()) != (rate, 2, 1):
                raise ValueError("Unexpected SAPI audio format")
            samples = array("h", stream.readframes(stream.getnframes()))
        active = [i for i, value in enumerate(samples) if abs(value) > 180]
        if not active:
            raise ValueError("SAPI generated a silent syllable")
        first, last = max(0, active[0] - round(rate * 0.02)), min(len(samples), active[-1] + round(rate * 0.03))
        samples = samples[first:last]
        start = len(audio) / rate
        audio.extend(samples)
        end = len(audio) / rate
        visemes = segment["visemes"]
        if len(visemes) == 1:
            timings = [(start, end, visemes[0])]
        else:
            consonant = min(0.09, (end - start) / 4)
            timings = [(max(0, start - 0.06), start + consonant, visemes[0])]
            remainder = (end - start - consonant) / (len(visemes) - 1)
            timings += [(start + consonant + j * remainder, start + consonant + (j + 1) * remainder, v)
                        for j, v in enumerate(visemes[1:])]
            # Preserve real silence outside the planned pre-articulation interval.
            pauses[-1] = (pauses[-1][0], max(pauses[-1][0], timings[0][0]))
        events.extend({"start": a, "end": b, "viseme": v, "strength": 1.0} for a, b, v in timings)
        segments.append({"text": segment["text"], "start": start, "end": end})
        gap = 0.25 if index + 1 == len(request["segments"]) else 0.16
        audio.extend([0] * round(rate * gap))
        pauses.append((end, len(audio) / rate))
    audio_path = output / "audio.wav"
    with wave.open(str(audio_path), "wb") as stream:
        stream.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        stream.writeframes(audio.tobytes())
    duration = len(audio) / rate
    voice = json.loads((raw / "voice.json").read_text("utf-8-sig"))
    bundle = {"schema_version": 1, "source": "mock-tts-windows-sapi", "voice": voice["voice"],
              "alignment": "synthetic-syllable-timing-not-forced-alignment", "text": request["text"],
              "audio_file": "audio.wav", "audio_sha256": binary_hash(audio_path),
              "duration_seconds": duration, "sample_rate": rate,
              "events": events, "segments": segments, "pause_ranges": pauses}
    bundle_path = output / "tts.json"
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    load_bundle(bundle_path)
    config = json.loads((PROJECT / "configs/head-draft.json").read_text("utf-8-sig"))
    config["scene"]["camera"] = "head-closeup"
    config["quality"].update(width=960, height=540, samples=8)
    config["performance"].update(text=request["text"], tts_file=str(bundle_path),
                                  frames=math.ceil(duration * config["quality"]["fps"]) + 2)
    config_path = output / "render-config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source": bundle["source"], "duration_seconds": duration,
                      "viseme_events": len(events), "render_config": str(config_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

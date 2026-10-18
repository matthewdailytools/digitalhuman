"""Provider-independent TTS audio + viseme contract. Times are seconds on the audio clock."""
import hashlib
import json
import math
from pathlib import Path
import wave

# Half width, half opening, protrusion and jaw weight; intentionally simplified anatomy.
MOUTH_SHAPES = {
    "REST": (0.052, 0.0002, 0.0, 0.0),
    "MBP": (0.050, 0.0001, 0.001, 0.0),
    "A": (0.057, 0.032, 0.004, 0.85),
    "E": (0.071, 0.014, 0.002, 0.35),
    "I": (0.073, 0.008, 0.001, 0.22),
    "O": (0.034, 0.027, 0.020, 0.65),
    "U": (0.026, 0.016, 0.025, 0.35),
    "FV": (0.049, 0.006, 0.004, 0.10),
}


def binary_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_bundle(data):
    if data.get("schema_version") != 1 or not isinstance(data.get("text"), str):
        raise ValueError("Invalid speech schema/text")
    if not isinstance(data.get("audio_file"), str) or not data["audio_file"]:
        raise ValueError("Speech requires an audio_file")
    digest = data.get("audio_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Speech requires a lowercase SHA-256 audio hash")
    duration = data.get("duration_seconds")
    if not number(duration) or not 0 < duration <= 30:
        raise ValueError("Speech duration must be finite, positive and at most 30 seconds")
    if not isinstance(data.get("events"), list) or not data["events"]:
        raise ValueError("Speech requires a nonempty viseme event list")
    previous_end = 0.0
    for event in data["events"]:
        if not isinstance(event, dict):
            raise ValueError("Viseme events must be objects")
        start, end, strength = event.get("start"), event.get("end"), event.get("strength", 1.0)
        if (not all(number(v) for v in (start, end, strength)) or start < previous_end - 1e-8
                or start < 0 or end <= start or end > duration + 1e-8 or not 0 <= strength <= 1):
            raise ValueError("Invalid, overlapping, unordered or out-of-range viseme timestamps/strength")
        if event.get("viseme") not in MOUTH_SHAPES:
            raise ValueError("Unknown viseme")
        previous_end = end


def load_bundle(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text("utf-8-sig"))
    validate_bundle(data)
    audio = Path(data["audio_file"])
    if not audio.is_absolute():
        audio = path.parent / audio
    audio = audio.resolve()
    if binary_hash(audio) != data["audio_sha256"]:
        raise ValueError("TTS audio hash does not match its timing bundle")
    with wave.open(str(audio), "rb") as stream:
        duration = stream.getnframes() / stream.getframerate()
        if abs(duration - data["duration_seconds"]) > 1 / stream.getframerate() + 1e-7:
            raise ValueError("TTS audio duration and timing bundle differ")
    data["audio_file"] = str(audio)
    return data


def viseme_weights(time_seconds, events, transition=0.055):
    """Continuous transitions for adjacent events; exact neutral in gaps and after the utterance."""
    result = {name: 0.0 for name in MOUTH_SHAPES if name != "REST"}
    for index, event in enumerate(events):
        start, end = event["start"], event["end"]
        if not start <= time_seconds < end:
            continue
        if event["viseme"] == "REST":
            return result
        previous = events[index - 1] if index else None
        following = events[index + 1] if index + 1 < len(events) else None
        width = min(transition, (end - start) / 3)
        blend = min(1.0, (time_seconds - start) / width)
        blend = blend * blend * (3 - 2 * blend)
        if event["viseme"] != "REST":
            result[event["viseme"]] += blend * event.get("strength", 1.0)
        if previous and abs(previous["end"] - start) < 1e-8 and previous["viseme"] != "REST":
            result[previous["viseme"]] += (1 - blend) * previous.get("strength", 1.0)
        if not following or following["viseme"] == "REST" or following["start"] - end > 1e-8:
            release = min(1.0, (end - time_seconds) / width)
            release = release * release * (3 - 2 * release)
            result = {key: value * release for key, value in result.items()}
        return result
    return result

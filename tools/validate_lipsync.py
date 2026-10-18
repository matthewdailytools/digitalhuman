"""Inspect evaluated Blender mouth geometry and compare its baked timeline with TTS events."""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
from speech import load_bundle

parser = argparse.ArgumentParser()
parser.add_argument("--tts-file", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--render-previews", action="store_true")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
bundle = load_bundle(args.tts_file)
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
fps = scene.render.fps
mouth = bpy.data.objects["MouthInterior"]
keys = bpy.data.objects["MouthLips"].data.shape_keys.key_blocks
states, errors = {}, []


def sample(time_seconds):
    frame = round(time_seconds * fps) + 1
    assert 1 <= frame <= scene.frame_end
    scene.frame_set(frame)
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = mouth.evaluated_get(graph)
    mesh = evaluated.to_mesh()
    xs, zs = [v.co.x for v in mesh.vertices], [v.co.z for v in mesh.vertices]
    dimensions = (max(xs) - min(xs), max(zs) - min(zs))
    evaluated.to_mesh_clear()
    weights = {key.name: key.value for key in keys if key.name != "Basis"}
    return frame, dimensions, weights


for event in bundle["events"]:
    middle = (event["start"] + event["end"]) / 2
    frame, (width, opening), weights = sample(middle)
    assert weights[event["viseme"]] > 0.65, (frame, event, weights)
    errors.append(abs((frame - 1) / fps - middle))
    states.setdefault(event["viseme"], {"frame": frame, "width_m": width,
                                      "opening_m": opening, "weight": weights[event["viseme"]]})
    if event["viseme"] == "MBP":
        assert opening < 0.001

pause_count = 0
for start, end in bundle["pause_ranges"]:
    if end - start < 1 / fps:
        continue
    frame, (width, opening), weights = sample((start + end) / 2)
    assert max(weights.values()) < 1e-5, (frame, weights)
    assert opening < 0.001
    states.setdefault("REST", {"frame": frame, "width_m": width, "opening_m": opening})
    pause_count += 1

assert states["A"]["opening_m"] > 0.04
assert states["O"]["width_m"] < states["A"]["width_m"] - 0.02
assert states["E"]["width_m"] > states["A"]["width_m"] + 0.02
assert states["U"]["width_m"] < states["O"]["width_m"] - 0.005
assert set(states) == {"REST", "MBP", "A", "E", "I", "O", "U", "FV"}
scene.frame_set(scene.frame_end)
assert all(key.value < 1e-5 for key in keys if key.name != "Basis")
assert max(errors) <= 0.5 / fps + 1e-7
if args.render_previews:
    for name, state in states.items():
        scene.frame_set(state["frame"])
        scene.render.filepath = str(output / f"mouth_{name}.png")
        bpy.ops.render.render(write_still=True)
report = {"passed": True, "source": bundle["source"], "alignment": bundle["alignment"],
          "states": states, "event_checks": len(bundle["events"]), "pause_checks": pause_count,
          "last_frame_closed": True, "max_frame_quantization_ms": round(max(errors) * 1000, 3),
          "note": "Frame quantization of synthetic event midpoints; not measured phoneme accuracy"}
(output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))

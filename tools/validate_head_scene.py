"""Validate the saved prototype in Blender, including evaluated animation and camera bounds."""
import argparse
import json
from pathlib import Path
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
scene = bpy.context.scene
head = bpy.data.objects["HeadControl"]
body = bpy.data.objects["BodyControl"]
eyes = [bpy.data.objects[f"EyeAperture_{side}"] for side in (-1, 1)]
assert scene.render.fps == 24
assert scene.render.resolution_x == 1280 and scene.render.resolution_y == 720
assert scene.frame_end == 120
assert bpy.data.objects.get("Hair_StaticCap")
states = {}
for frame in (1, 23, 31, 53, 61, 91, 120):
    scene.frame_set(frame)
    states[str(frame)] = {
        "head_z": round(head.rotation_euler.z, 6),
        "body_z": round(body.location.z, 6),
        "eye_scale_z": [round(eye.scale.z, 6) for eye in eyes],
    }
    geometry = bpy.data.objects["Head"]
    for corner in geometry.bound_box:
        projected = world_to_camera_view(scene, scene.camera, geometry.matrix_world @ Vector(corner))
        assert 0 < projected.x < 1 and 0 < projected.y < 1 and projected.z > 0
assert all(value < 0.05 for value in states["23"]["eye_scale_z"])
assert all(value < 0.05 for value in states["53"]["eye_scale_z"])
assert states["1"]["eye_scale_z"] == [1.0, 1.0]
assert states["31"]["head_z"] > 0.1 and states["91"]["head_z"] < -0.1
assert states["61"]["body_z"] > states["1"]["body_z"]
assert abs(states["1"]["head_z"] - states["120"]["head_z"]) < 0.0001
assert abs(states["1"]["body_z"] - states["120"]["body_z"]) < 0.0001
result = {"passed": True, "frames": 120, "fps": 24, "camera_bounds_passed": True,
          "head_turn_passed": True, "simplified_blink_passed": True,
          "breath_passed": True, "loop_endpoints_passed": True, "samples": states}
Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))

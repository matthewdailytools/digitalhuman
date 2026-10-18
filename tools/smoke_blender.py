"""Run with Blender --background --factory-startup --python this_file -- --output PATH."""
import argparse
import json
from pathlib import Path
import sys

import bpy


parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
parser.add_argument("--engine", choices=["BLENDER_WORKBENCH", "BLENDER_EEVEE_NEXT"],
                    default="BLENDER_WORKBENCH")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=True)

scene = bpy.context.scene
scene.render.engine = args.engine
scene.render.resolution_x = 640
scene.render.resolution_y = 360
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(output / "smoke.png")
scene.render.fps = 24
scene.display.shading.light = "STUDIO"
bpy.ops.wm.save_as_mainfile(filepath=str(output / "smoke.blend"))
bpy.ops.render.render(write_still=True)
if not (output / "smoke.png").is_file():
    raise RuntimeError("Render did not produce a PNG")
(output / "result.json").write_text(json.dumps({
    "blender": bpy.app.version_string,
    "engine": scene.render.engine,
    "resolution": [640, 360],
    "blend_saved": (output / "smoke.blend").is_file(),
    "rendered": True,
    "scope": "Basic scene save and Workbench single-frame render; not a character benchmark"
}, indent=2), encoding="utf-8")

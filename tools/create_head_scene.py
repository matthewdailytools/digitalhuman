"""Procedural, deliberately simplified head/bust for pipeline validation in Blender 4.5."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from speech import MOUTH_SHAPES, load_bundle, viseme_weights


def material(name, color, roughness=0.65):
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1)
    result.use_nodes = True
    principled = result.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (*color, 1)
    principled.inputs["Roughness"].default_value = roughness
    return result


def sphere(name, location, scale, mat, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=20, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    if parent:
        obj.parent = parent
    return obj


def mesh(name, vertices, faces, mat, parent=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    obj.parent = parent
    for polygon in data.polygons:
        polygon.use_smooth = True
    return obj


def curve(name, points, radius, mat, parent=None):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = radius
    data.bevel_resolution = 2
    spline = data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for target, point in zip(spline.points, points):
        target.co = (*point, 1)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    obj.parent = parent
    return obj


def empty(name, location):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    return obj


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def mouth_vertices(shape, interior=False):
    width, opening, protrusion, _ = MOUTH_SHAPES[shape]
    if interior:
        points = [(0, -0.197 - protrusion, 0.213)]
        points += [(width * math.cos(t * math.tau / 48), -0.197 - protrusion,
                    0.213 + opening * math.sin(t * math.tau / 48)) for t in range(48)]
        return points
    points = []
    for i in range(48):
        theta = i * math.tau / 48
        for j in range(8):
            phi = j * math.tau / 8
            thickness = 0.0035
            points.append(((width + thickness * math.cos(phi)) * math.cos(theta),
                           -0.200 - protrusion + thickness * math.sin(phi),
                           0.213 + (opening + thickness * math.cos(phi)) * math.sin(theta)))
    return points


def create_mouth(head, face, lip_material, interior_material):
    lip_faces = []
    for i in range(48):
        for j in range(8):
            lip_faces.append((i * 8 + j, i * 8 + (j + 1) % 8,
                              ((i + 1) % 48) * 8 + (j + 1) % 8, ((i + 1) % 48) * 8 + j))
    cavity_faces = [(0, i + 1, (i + 1) % 48 + 1) for i in range(48)]
    objects = []
    for name, interior, faces, mat in (("MouthLips", False, lip_faces, lip_material),
                                        ("MouthInterior", True, cavity_faces, interior_material)):
        obj = mesh(name, mouth_vertices("REST", interior), faces, mat, head)
        obj.shape_key_add(name="Basis")
        for shape in MOUTH_SHAPES:
            if shape == "REST":
                continue
            key = obj.shape_key_add(name=shape)
            for vertex, coordinate in zip(key.data, mouth_vertices(shape, interior)):
                vertex.co = coordinate
        objects.append(obj)
    face.shape_key_add(name="Basis")
    jaw = face.shape_key_add(name="JawOpen")
    for vertex in jaw.data:
        if vertex.co.z < -0.25:
            vertex.co.z -= 0.06 * min(1, (-vertex.co.z - 0.25) / 0.75)
    return objects, jaw


def build_scene(width, height, frames, hair, fps=24, samples=16, camera_mode="fixed-half-body", speech=None):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    skin = material("Skin_Draft", (0.56, 0.32, 0.22))
    lips = material("Lip_Draft", (0.27, 0.095, 0.075))
    dark = material("Hair_Draft", (0.035, 0.025, 0.021))
    white = material("Sclera_Draft", (0.82, 0.84, 0.81), 0.35)
    iris = material("Iris_Draft", (0.055, 0.10, 0.085), 0.3)
    pupil = material("Pupil_Draft", (0.005, 0.006, 0.005), 0.3)
    shirt = material("Shirt_Draft", (0.045, 0.105, 0.14))
    backdrop = material("Backdrop", (0.12, 0.15, 0.17))
    body = empty("BodyControl", (0, 0, 0))
    # Head child geometry is authored in local coordinates about the neck pivot.
    head = empty("HeadControl", (0, 0, 1.64))
    head.parent = body
    face = sphere("Head", (0, 0, 0.34), (0.225, 0.20, 0.30), skin, head)
    for vertex in face.data.vertices:
        if vertex.co.z < -0.25:
            vertex.co.x *= 0.82 + 0.18 * (vertex.co.z + 1) / 0.75
    sphere("Neck", (0, 0.015, 1.58), (0.087, 0.085, 0.20), skin, body)
    profile = [(0.65, 0.30, 0.15), (0.8, 0.33, 0.17), (1.0, 0.35, 0.18),
               (1.20, 0.39, 0.18), (1.32, 0.43, 0.17), (1.39, 0.41, 0.15),
               (1.46, 0.27, 0.12), (1.50, 0.09, 0.085)]
    vertices, faces = [], []
    for z, radius_x, radius_y in profile:
        for j in range(48):
            phi = 2 * math.pi * j / 48
            vertices.append((radius_x * math.cos(phi), 0.035 + radius_y * math.sin(phi), z))
    for i in range(len(profile) - 1):
        for j in range(48):
            a, b = i * 48 + j, i * 48 + (j + 1) % 48
            faces.append((a, b, b + 48, a + 48))
    mesh("Torso_Shirt", vertices, faces, shirt, body)
    for side in (-1, 1):
        sphere(f"Ear_{side}", (side * 0.222, 0.005, 0.34), (0.037, 0.025, 0.065), skin, head)
        sphere(f"EarInset_{side}", (side * 0.236, -0.014, 0.34), (0.014, 0.01, 0.035), lips, head)
    sphere("NoseBridge", (0, -0.19, 0.345), (0.027, 0.035, 0.076), skin, head)
    sphere("NoseTip", (0, -0.225, 0.305), (0.035, 0.035, 0.025), skin, head)
    for side in (-1, 1):
        sphere(f"Nostril_{side}", (side * 0.021, -0.246, 0.295), (0.008, 0.005, 0.004), lips, head)
    interior = material("MouthInterior_Draft", (0.022, 0.004, 0.005))
    mouths, jaw = create_mouth(head, face, lips, interior)
    eyes = []
    for side in (-1, 1):
        eye = empty(f"EyeAperture_{side}", (side * 0.087, -0.182, 0.405))
        eye.parent = head
        eyes.append(eye)
        sphere(f"EyeWhite_{side}", (0, 0, 0), (0.052, 0.029, 0.024), white, eye)
        sphere(f"Iris_{side}", (0, -0.028, 0), (0.016, 0.0035, 0.016), iris, eye)
        sphere(f"Pupil_{side}", (0, -0.031, 0), (0.007, 0.0015, 0.007), pupil, eye)
        eyebrow = [(side * 0.087 + 0.052 * x / 10, -0.183,
                    0.452 + 0.009 * (1 - (x / 10) ** 2)) for x in range(-10, 11)]
        curve(f"Eyebrow_{side}", eyebrow, 0.0045, dark, head)
    if hair == "static":
        vertices, faces = [], []
        rings, segments = 14, 48
        for i in range(rings + 1):
            for j in range(segments):
                phi = 2 * math.pi * j / segments
                front = max(0, -math.sin(phi))
                limit = 1.66 - 0.69 * front ** 2
                theta = 0.015 + (limit - 0.015) * i / rings
                vertices.append((0.232 * math.sin(theta) * math.cos(phi),
                                 0.207 * math.sin(theta) * math.sin(phi),
                                 0.34 + 0.31 * math.cos(theta)))
        for i in range(rings):
            for j in range(segments):
                a = i * segments + j
                b = i * segments + (j + 1) % segments
                faces.append((a, b, b + segments, a + segments))
        mesh("Hair_StaticCap", vertices, faces, dark, head)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = samples
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.fps = fps
    scene.frame_start, scene.frame_end = 1, frames
    scene.world.color = (0.15, 0.15, 0.15)
    scene.view_settings.view_transform = "AgX"
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0.49))
    bpy.context.object.name = "Ground"
    bpy.context.object.data.materials.append(backdrop)
    bpy.ops.object.camera_add(location=(0.13, -4.5, 2.0))
    camera = bpy.context.object
    camera.name = "Camera_HalfBody"
    camera.data.type = "ORTHO"
    # Ortho scale is the horizontal extent at this aspect ratio; include the full bust.
    camera.data.ortho_scale = 3.45
    aim(camera, (0, 0, 1.49))
    if camera_mode == "head-closeup":
        camera.data.ortho_scale = 1.28
        aim(camera, (0, 0, 1.99))
    scene.camera = camera
    for name, location, power, size in [
        ("Key", (-2, -3, 4), 400, 3),
        ("Fill", (2, -1.5, 2.5), 160, 2.5),
        ("Rim", (0.5, 1.5, 3.5), 350, 2),
    ]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size = power, "DISK", size
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = location
        aim(obj, (0, 0, 1.7))
    # A closed periodic sequence: blink around frames 23 and 53; subtle turn and breath.
    mouth_timeline = []
    for frame in range(1, frames + 1):
        phase = (frame - 1) / max(1, frames - 1) * 2 * math.pi
        head.rotation_euler = (math.radians(1.2) * math.sin(phase * 2), 0,
                               math.radians(7) * math.sin(phase))
        head.keyframe_insert("rotation_euler", frame=frame)
        body.location.z = 0.003 * (1 - math.cos(phase))
        body.keyframe_insert("location", frame=frame)
        blink = max(max(0, 1 - abs(frame - center) / max(1, fps / 8))
                    for center in (round(23 * fps / 24), round(53 * fps / 24)))
        for eye in eyes:
            eye.scale.z = 1 - blink * 0.96
            eye.keyframe_insert("scale", frame=frame)
        time_seconds = (frame - 1) / fps
        weights = viseme_weights(time_seconds, speech["events"]) if speech else {v: 0 for v in MOUTH_SHAPES if v != "REST"}
        for obj in mouths:
            for name, weight in weights.items():
                key = obj.data.shape_keys.key_blocks[name]
                key.value = weight
                key.keyframe_insert("value", frame=frame)
        jaw.value = sum(weights[name] * MOUTH_SHAPES[name][3] for name in weights)
        jaw.keyframe_insert("value", frame=frame)
        mouth_timeline.append({"frame": frame, "time": time_seconds, "weights": weights, "jaw": jaw.value})
    scene["asset_revision"] = "procedural-head-v1"
    scene["scope"] = "Technical mannequin; simplified eye aperture and mouth Shape Keys; not photoreal"
    scene["axes"] = "Z up; front -Y; units meters"
    scene.frame_set(1)
    # Open directly in the camera view using a low-cost solid viewport.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
                area.spaces.active.shading.type = "SOLID"
                area.spaces.active.shading.color_type = "MATERIAL"
    return scene, mouth_timeline


parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
parser.add_argument("--width", type=int, default=1280)
parser.add_argument("--height", type=int, default=720)
parser.add_argument("--frames", type=int, default=72)
parser.add_argument("--fps", type=int, default=24)
parser.add_argument("--samples", type=int, default=16)
parser.add_argument("--hair", choices=["none", "static"], default="static")
parser.add_argument("--render", choices=["still", "animation", "none"], default="still")
parser.add_argument("--camera", choices=["fixed-half-body", "head-closeup"], default="fixed-half-body")
parser.add_argument("--tts-file")
parser.add_argument("--still-frame", type=int, default=1)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
if args.width <= 0 or args.height <= 0 or args.frames < 2 or args.fps < 1 or args.samples < 1:
    raise ValueError("Positive dimensions and at least two frames are required")
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
speech = load_bundle(args.tts_file) if args.tts_file else None
if speech and speech["duration_seconds"] > args.frames / args.fps:
    raise ValueError("Speech exceeds scene timeline")
scene, mouth_timeline = build_scene(args.width, args.height, args.frames, args.hair, args.fps, args.samples, args.camera, speech)
if args.render == "still":
    if not 1 <= args.still_frame <= args.frames:
        raise ValueError("still-frame outside scene timeline")
    scene.frame_set(args.still_frame)
scene.render.filepath = str(output / ("frame_" if args.render == "animation" else "preview.png"))
assert scene.camera and bpy.data.objects.get("HeadControl") and bpy.data.objects.get("Head")
assert len(bpy.data.objects["Head"].data.vertices) < 10000
bpy.ops.wm.save_as_mainfile(filepath=str(output / "head-v1.blend"))
started = time.perf_counter()
if args.render == "animation":
    bpy.ops.render.render(animation=True)
elif args.render == "still":
    bpy.ops.render.render(write_still=True)
report = {
    "blender": bpy.app.version_string, "revision": scene["asset_revision"],
    "engine": scene.render.engine, "samples": scene.eevee.taa_render_samples,
    "width": args.width, "height": args.height, "fps": args.fps, "frames": args.frames,
    "hair": args.hair, "objects": len(scene.objects),
    "vertices": sum(len(o.data.vertices) for o in scene.objects if o.type == "MESH"),
    "render_mode": args.render, "render_seconds": round(time.perf_counter() - started, 3),
    "scope": scene["scope"],
    "speech_source": speech.get("source") if speech else None,
    "mouth_shapes": list(MOUTH_SHAPES), "camera": args.camera,
}
if args.render == "animation":
    files = list(output.glob("frame_*.png"))
    if len(files) != args.frames:
        raise RuntimeError(f"Expected {args.frames} rendered frames, got {len(files)}")
    report["frames_written"] = len(files)
(output / "scene-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
(output / "mouth-timeline.json").write_text(json.dumps(mouth_timeline, indent=2), encoding="utf-8")

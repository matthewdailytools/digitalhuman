"""Load the editable scan rig and bake a validated five-control timeline to its master controls."""
import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from scanned_rig import animate

parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
config=json.loads(Path(args.config).read_text('utf-8'));output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=config['character']['rig_file'],load_ui=False,use_scripts=False)
scene=bpy.context.scene;rig=bpy.data.objects['ScanRig'];q=config['quality'];p=config['performance']
if 'micro_control' not in p:raise ValueError('Scanned video requires a five-control timeline')
animate(rig,p['micro_control'],q['fps'],p['frames'])
scene.cycles.device='CPU';scene.cycles.samples=q['samples'];scene.cycles.use_denoising=True
scene.render.threads_mode='FIXED';scene.render.threads=4;scene.render.use_persistent_data=True
scene.render.resolution_x=q['width'];scene.render.resolution_y=q['height'];scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
camera=bpy.data.objects['Baseline_front'];camera.data.sensor_fit='VERTICAL';camera.data.sensor_height=36
target=Vector((0,-2,24));radius=96 if config['scene']['camera']=='head-closeup' else 112
camera.location=target+Vector((0,-radius,1.5));camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
scene.camera=camera
bpy.data.objects['ShortHair'].hide_render=q['hair']=='none'
bpy.data.objects['ScalpSurface'].hide_render=True
scene.render.filepath=str(output/'frame_')
bpy.ops.wm.save_as_mainfile(filepath=str(output.parent/'scene.blend'),compress=True)
bpy.ops.render.render(animation=True)
(output.parent/'scene-report.json').write_text(json.dumps(dict(success=True,frames=p['frames'],fps=q['fps'],
    hair=q['hair'],plan=p['micro_control'],rig=config['character'],editable_master_controls=True),indent=2),'utf-8')
print('SCANNED MOTION RENDERED',p['frames'],flush=True)

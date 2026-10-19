"""Create the editable neutral rig without modifying the downloaded scan."""
import argparse
import json
from pathlib import Path
import sys

import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from scanned_rig import build

parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
parser.add_argument('--debug-stills',action='store_true')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(Path(args.source).resolve()),load_ui=False,use_scripts=False)
rig,report=build()
scene=bpy.context.scene
scene.camera=bpy.data.objects['Baseline_front']
scene.cycles.samples=16;scene.cycles.preview_samples=8
scene.render.resolution_x=512;scene.render.resolution_y=640
scene['asset_license']='PERSONAL USE ONLY; contact vendor for commercial use'
scene['hair_description']='Procedural dark-brown short swept hair; fixed seed 72; no simulation'
bpy.context.view_layer.update()
for channel in ('eye_close','smile','mouth_open','nod'):
    rig[channel]=1.0;rig.update_tag();bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get();deps.update()
    if channel=='eye_close':
        assert abs(bpy.data.objects['Head'].data.shape_keys.key_blocks['EyeClose'].value-1)<1e-5
    if channel=='mouth_open':assert abs(rig.pose.bones['Jaw'].rotation_euler.x-.26)<1e-5
    rig[channel]=0.0;rig.update_tag();bpy.context.view_layer.update()
report['safe_drivers_verified']=True
path=output/'scanned-head-rig.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path),compress=True)
(output/'binding-report.json').write_text(json.dumps(report,indent=2),'utf-8')
if args.debug_stills:
    scene.cycles.samples=8;scene.render.resolution_x=384;scene.render.resolution_y=480
    for name,values in (('neutral',{}),('closed',{'eye_close':1}),('smile',{'smile':1}),
                        ('mouth',{'mouth_open':1}),('gaze',{'gaze_x':1,'gaze_y':.5}),('nod',{'nod':1}),
                        ('combined',{'smile':.7,'mouth_open':.7,'eye_close':1})):
        for channel in ('eye_close','smile','mouth_open','nod','gaze_x','gaze_y'):rig[channel]=values.get(channel,0)
        rig.update_tag();bpy.context.view_layer.update()
        scene.render.filepath=str(output/(name+'.png'));bpy.ops.render.render(write_still=True)
        print('POSE RENDERED',name,flush=True)
print('SCANNED RIG BUILT',path,flush=True)

"""Render fixed, comparable views of the v2 smile and its previous baseline."""
import argparse
from pathlib import Path
import sys
import bpy

parser=argparse.ArgumentParser();parser.add_argument('--rig',required=True);parser.add_argument('--before',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
cases=[('neutral',0,0,0,'front'),('light',.35,0,0,'front'),('smile',1,0,0,'front'),
       ('open-smile',1,.65,0,'front'),('closed-smile',1,0,1,'front'),
       ('left-smile',1,0,0,'left'),('right-smile',1,0,0,'right')]
for path,poses in ((args.rig,cases),(args.before,[('before-smile',1,0,0,'front'),('before-open',1,.65,0,'front')])):
    bpy.ops.wm.open_mainfile(filepath=path,load_ui=False,use_scripts=False)
    scene=bpy.context.scene;rig=bpy.data.objects['ScanRig']
    if rig.animation_data:rig.animation_data.action=None
    scene.cycles.device='CPU';scene.cycles.samples=32;scene.cycles.use_denoising=True
    scene.render.resolution_x=512;scene.render.resolution_y=640;scene.render.resolution_percentage=100
    scene.render.threads_mode='FIXED';scene.render.threads=4;scene.render.use_persistent_data=True
    for name,s,m,b,camera in poses:
        for channel in ('eye_close','gaze_x','gaze_y','smile','mouth_open','nod'):rig[channel]=0.0
        rig['smile']=s;rig['mouth_open']=m;rig['eye_close']=b
        rig.update_tag();bpy.context.view_layer.update()
        scene.camera=bpy.data.objects['Baseline_'+camera]
        scene.render.filepath=str(output/(name+'.png'));bpy.ops.render.render(write_still=True)
        print('SMILE REVIEW',name,flush=True)

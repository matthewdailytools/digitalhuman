"""Render short-hair reference portraits from the actual rig asset, at neutral controls."""
import argparse
import json
from pathlib import Path
import sys
import bpy

parser=argparse.ArgumentParser();parser.add_argument('--rig',required=True);parser.add_argument('--output',required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
bpy.ops.wm.open_mainfile(filepath=args.rig,load_ui=False,use_scripts=False)
scene=bpy.context.scene;scene.cycles.samples=48;scene.cycles.device='CPU'
scene.render.resolution_x=768;scene.render.resolution_y=960
scene.render.threads_mode='FIXED';scene.render.threads=4
output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
for name in ('front','left','right'):
    scene.camera=bpy.data.objects['Baseline_'+name]
    scene.render.filepath=str(output/(name+'.png'))
    bpy.ops.render.render(write_still=True)
    print('HAIR PORTRAIT RENDERED',name,flush=True)

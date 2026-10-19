"""Measure evaluated smile regions and corrective effect in the actual Blender asset."""
import argparse
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

parser=argparse.ArgumentParser();parser.add_argument('--blend',required=True);parser.add_argument('--output',required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
bpy.ops.wm.open_mainfile(filepath=args.blend,load_ui=False,use_scripts=False)
rig=bpy.data.objects['ScanRig'];head=bpy.data.objects['Head']
if rig.animation_data:rig.animation_data.action=None
channels=('eye_close','gaze_x','gaze_y','smile','mouth_open','nod')
for modifier in head.modifiers:
    if modifier.type=='SUBSURF':modifier.show_viewport=False
keys=head.data.shape_keys.key_blocks
required=('SmileCorners','SmileCheeks','SmileLids','SmileOpenCorrective')
assert all(name in keys for name in required)

def pose(smile=0,mouth=0,blink=0):
    for channel in channels:rig[channel]=0.0
    rig['smile']=float(smile);rig['mouth_open']=float(mouth);rig['eye_close']=float(blink)
    rig.update_tag();head.data.update();bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get();deps.update()
    obj=head.evaluated_get(deps)
    return [obj.matrix_world@v.co for v in obj.data.vertices]

neutral=pose()
def nearest(p):return min(range(len(neutral)),key=lambda i:(neutral[i]-Vector(p)).length)
landmarks=json.loads((Path(__file__).resolve().parents[1]/'configs/scanned-head-landmarks.json').read_text())
corners=[nearest((x,-12.5,23.8)) for x in (-2.35,2.35)]
cheeks=[nearest((x,-11,26.7)) for x in (-3.8,3.8)]
lids=[nearest((cx,-11.5,cz-.43)) for cx,cy,cz in landmarks['eye_centers']]
smiling=pose(1)
corner_lifts=[smiling[i].z-neutral[i].z for i in corners]
cheek_lifts=[smiling[i].z-neutral[i].z for i in cheeks]
lid_lifts=[smiling[i].z-neutral[i].z for i in lids]
assert min(corner_lifts)>.2,corner_lifts
assert min(cheek_lifts)>.1,cheek_lifts
assert min(lid_lifts)>.015,lid_lifts
corrected=pose(1,1)
keys['SmileOpenCorrective'].mute=True
uncorrected=pose(1,1)
keys['SmileOpenCorrective'].mute=False
reductions=[abs(uncorrected[i].x)-abs(corrected[i].x) for i in corners]
assert min(reductions)>.05,reductions
grid=[]
for s in (0,.35,.7,1):
    for m in (0,.5,1):
        p=pose(s,m)
        for name,value in (('SmileCorners',s),('SmileCheeks',s),('SmileLids',s),('SmileOpenCorrective',s*m)):
            assert abs(keys[name].value-value)<1e-5,(s,m,name)
        upper,lower=[p[landmarks[k]] for k in ('upper_lip_rim','lower_lip_rim')]
        gap=upper.z-lower.z
        # Neutral scan has a slightly overlapping seam; opened poses must separate.
        if m>=.5:assert gap>.7,(s,m,gap)
        maximum=max((a-b).length for a,b in zip(p,neutral))
        assert maximum<4,(s,m,maximum)
        grid.append(dict(smile=s,mouth_open=m,vertical_lip_gap_cm=gap,max_displacement_cm=maximum))
# Full closure must be identical with and without the smile lid layer.
pose(1,0,1)
for name in ('Head','Lashes','Eye Wet'):
    obj=bpy.data.objects[name];assert abs(obj.data.shape_keys.key_blocks['SmileLids'].value)<1e-6
    assert all(c.driver.is_valid for c in obj.data.shape_keys.animation_data.drivers)
skin=BVHTree.FromObject(head,bpy.context.evaluated_depsgraph_get());covered=0
for cx,cy,cz in landmarks['eye_centers']:
    for dx in (-.65,-.3,0,.3,.65):
        for dz in (-.22,0,.22):
            loc,*_=skin.ray_cast(Vector((cx+dx,-50,cz+dz)),Vector((0,1,0)),80)
            covered+=int(loc is not None and loc.y<cy-1.25)
assert covered==30,covered
pose()
assert all(keys[name].value==0 for name in required)
report=dict(success=True,shape_keys=list(required),corner_lifts_cm=corner_lifts,cheek_lifts_cm=cheek_lifts,
            lower_lid_lifts_cm=lid_lifts,open_smile_corner_width_reduction_per_side_cm=reductions,
            parameter_grid=grid,smiling_full_blink_rays_covered=covered,
            limitation='Procedural friendly-smile sample; no claim of muscle physics or full-face collision proof')
Path(args.output).parent.mkdir(parents=True,exist_ok=True)
Path(args.output).write_text(json.dumps(report,indent=2),'utf-8');print(json.dumps(report,indent=2))

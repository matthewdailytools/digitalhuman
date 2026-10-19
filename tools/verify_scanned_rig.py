"""Validate evaluated anatomy, eye occlusion, hair attachment, and optional clip frames."""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from micro_control import sample_plan

parser=argparse.ArgumentParser();parser.add_argument('--blend',required=True);parser.add_argument('--output',required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
bpy.ops.wm.open_mainfile(filepath=str(Path(args.blend).resolve()),load_ui=False,use_scripts=False)
scene=bpy.context.scene;rig=bpy.data.objects['ScanRig'];head=bpy.data.objects['Head']
landmarks=json.loads((ROOT/'configs/scanned-head-landmarks.json').read_text('utf-8'))
channels=('eye_close','gaze_x','gaze_y','smile','mouth_open','nod')
clip_checks=0;peaks={key:0 for key in channels}
if 'micro_control_plan' in scene:
    plan=json.loads(scene['micro_control_plan'])
    for frame in range(scene.frame_start,scene.frame_end+1):
        scene.frame_set(frame);bpy.context.view_layer.update()
        expected=sample_plan(plan,(frame-1)/scene.render.fps);expected['nod']=expected.pop('pitch')/math.radians(12)
        for channel in channels:
            assert abs(rig[channel]-expected[channel])<1e-5,(frame,channel,rig[channel],expected[channel])
            peaks[channel]=max(peaks[channel],abs(rig[channel]))
        assert abs(head.data.shape_keys.key_blocks['EyeClose'].value-expected['eye_close'])<1e-5
        assert abs(rig.pose.bones['Jaw'].rotation_euler.x-.26*expected['mouth_open'])<1e-5
        clip_checks+=1
    rig.animation_data.action=None

def set_pose(**values):
    for channel in channels:rig[channel]=float(values.get(channel,0))
    rig.update_tag();bpy.context.view_layer.update();bpy.context.evaluated_depsgraph_get().update()

for obj in (head,bpy.data.objects['Lashes'],bpy.data.objects['Eye Wet']):
    for curve in obj.data.shape_keys.animation_data.drivers:
        assert curve.driver.is_valid,'Invalid shape driver'
for curve in rig.animation_data.drivers if rig.animation_data else []:
    assert curve.driver.is_valid,'Invalid skeleton driver'
# Geometry tests use the original vertex IDs before subdivision.
subdivisions=[m for m in head.modifiers if m.type=='SUBSURF']
for modifier in subdivisions:modifier.show_viewport=False
def positions(indices):
    deps=bpy.context.evaluated_depsgraph_get();obj=head.evaluated_get(deps)
    return [obj.matrix_world@obj.data.vertices[i].co for i in indices]
ids=[landmarks['upper_lip_rim'],landmarks['lower_lip_rim'],landmarks['upper_lip_seed'],landmarks['lower_lip_seed']]
set_pose();neutral=positions(ids)
for side,center in zip(('Left','Right'),landmarks['eye_centers']):
    obj=bpy.data.objects['Realtime Eyeball '+side]
    actual=sum((obj.matrix_world@Vector(p) for p in obj.bound_box),Vector())/8
    assert (actual-Vector(center)).length<.001,('Neutral eye moved',side,list(actual))
set_pose(mouth_open=1);opened=positions(ids)
gap_before=abs(neutral[0].z-neutral[1].z);gap_after=abs(opened[0].z-opened[1].z)
assert gap_after-gap_before>1.5,('Lip did not open',gap_before,gap_after)
assert (opened[0]-neutral[0]).length<.001,'Upper lip incorrectly assigned to jaw'
set_pose(smile=1);smile=positions(ids)
assert (smile[2]-neutral[2]).length>.02,'Smile did not deform upper lip'
set_pose(gaze_x=1,gaze_y=1)
assert abs(bpy.data.objects['EyePivot_Left'].rotation_euler.z-.24)<1e-5
assert abs(bpy.data.objects['EyePivot_Right'].rotation_euler.x+.16)<1e-5
for modifier in subdivisions:modifier.show_viewport=True
set_pose(eye_close=1)
deps=bpy.context.evaluated_depsgraph_get();skin=BVHTree.FromObject(head,deps)
occluded=0;tested=0
for cx,cy,cz in landmarks['eye_centers']:
    for dx in (-.65,-.3,0,.3,.65):
        for dz in (-.22,0,.22):
            location,normal,index,distance=skin.ray_cast(Vector((cx+dx,-50,cz+dz)),Vector((0,1,0)),80)
            tested+=1
            if location is not None and location.y<cy-1.25:occluded+=1
assert occluded==tested,('Closed eyelids do not cover the pupil region',occluded,tested)
set_pose(nod=.8)
assert abs(rig.pose.bones['Head'].rotation_euler.x-math.radians(10.8)*.8)<1e-5
deps=bpy.context.evaluated_depsgraph_get();scalp=bpy.data.objects['ScalpSurface']
surface=BVHTree.FromObject(scalp,deps);hair=bpy.data.objects['ShortHair']
maximum_distance=0
for strand in range(0,len(hair.data.curves),max(1,len(hair.data.curves)//80)):
    root=hair.matrix_world@hair.data.attributes['position'].data[strand*landmarks['hair_points']].vector
    nearest=surface.find_nearest(root)
    assert nearest[0] is not None
    maximum_distance=max(maximum_distance,(nearest[0]-root).length)
assert maximum_distance<.12,('Hair slips off scalp during nod',maximum_distance)
for vertex in head.data.vertices:
    assert abs(sum(group.weight for group in vertex.groups)-1)<1e-5,'Unnormalized face weights'
set_pose()
report=dict(success=True,editable_master_controls=list(channels),safe_drivers_with_autoexec_disabled=True,
            neutral_eye_centers_preserved=True,mouth_gap_before_cm=gap_before,mouth_gap_after_cm=gap_after,
            upper_lip_preserved=True,closed_eye_rays_covered=occluded,closed_eye_rays_tested=tested,
            hair_strands=len(hair.data.curves),hair_max_root_distance_during_nod_cm=maximum_distance,
            normalized_head_weights=True,clip_frames_checked=clip_checks,clip_peaks=peaks)
out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),'utf-8')
print(json.dumps(report,indent=2))

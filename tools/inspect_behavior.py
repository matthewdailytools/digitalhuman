"""Read actual saved Blender scenes; verify baked controls and their neutral endpoints."""
import bpy
import json
from pathlib import Path
import sys

arguments=sys.argv[sys.argv.index('--')+1:]
report_path=Path(arguments[0])
partial='--partial' in arguments[1:]
report=json.loads(report_path.read_text('utf-8-sig'))
results=[]
for case in report['cases']:
    name=case['name']
    if name not in ('expression-smile','expression-curious','expression-surprised','hair-sway','speech-02','speech-03','speech-04','preview-combined'):
        continue
    bpy.ops.wm.open_mainfile(filepath=str(Path(case['job'])/'frames/head-v1.blend'))
    scene=bpy.context.scene
    scene.frame_set(12)
    if name=='expression-smile':
        assert bpy.data.objects['MouthLips'].data.shape_keys.key_blocks['Smile'].value>0.3
    if name=='expression-curious':
        assert bpy.data.objects['Eyebrow_-1'].location.z>0.005
    if name=='expression-surprised':
        assert bpy.data.objects['EyeAperture_-1'].scale.z>1.05
    if name=='hair-sway':
        assert max(abs(v) for v in bpy.data.objects['HairControl'].rotation_euler)>0.005
    motion={'speech-02':'pitch','speech-03':'turn','speech-04':'arm'}.get(name)
    if motion:
        values=[]
        for frame in range(1,scene.frame_end+1):
            scene.frame_set(frame)
            obj=bpy.data.objects['GestureControl' if motion=='arm' else 'HeadControl']
            values.append(abs(obj.rotation_euler.x if motion in ('arm','pitch') else obj.rotation_euler.z))
        assert max(values)>0.05
    minimum_radius=None
    if name in ('hair-sway','preview-combined'):
        radii=[]
        cap=bpy.data.objects['Hair_StaticCap']
        for frame in range(1,scene.frame_end+1):
            scene.frame_set(frame)
            transform=bpy.data.objects['Head'].matrix_world.inverted() @ cap.matrix_world
            radii.extend((transform @ vertex.co).length for vertex in cap.data.vertices)
            radii.extend((transform @ polygon.center).length for polygon in cap.data.polygons)
        minimum_radius=min(radii)
        assert minimum_radius>1.0, f'Hair intersects analytic scalp: {minimum_radius}'
    scene.frame_set(scene.frame_end)
    for objname in ('HeadControl','GestureControl','HairControl'):
        assert max(abs(v) for v in bpy.data.objects[objname].rotation_euler)<1e-6
    assert bpy.data.objects['MouthLips'].data.shape_keys.key_blocks['Smile'].value<1e-6
    results.append({'case':name,'baked_scene_pass':True,'minimum_hair_scalp_radius':minimum_radius})
assert results and (partial or len(results)==8)
output=report_path.parent/('partial-baked-scene-checks.json' if partial else 'baked-scene-checks.json')
output.write_text(json.dumps(results,indent=2),'utf-8')
print('BAKED SCENES VALIDATED',len(results))

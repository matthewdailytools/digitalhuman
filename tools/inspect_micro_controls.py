"""Validate the actual saved Blender transforms and shape keys at every baked frame."""
import json
import math
from pathlib import Path
import sys
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from micro_control import sample_plan

path = Path(sys.argv[sys.argv.index('--')+1])
report = json.loads(path.read_text('utf-8-sig'))
results = []
for case in report['cases']:
    bpy.ops.wm.open_mainfile(filepath=str(Path(case['job'])/'frames/head-v1.blend'))
    scene = bpy.context.scene
    plan = case['config']['performance']['micro_control']
    fps = case['config']['quality']['fps']
    extrema = dict(eye_close=0,gaze_x=0,gaze_y=0,smile=0,mouth_open=0,pitch=0)
    for frame in range(1,scene.frame_end+1):
        scene.frame_set(frame)
        expected = sample_plan(plan,(frame-1)/fps)
        for key,value in expected.items():
            extrema[key] = max(extrema[key],abs(value))
        assert abs(bpy.data.objects['HeadControl'].rotation_euler.x-expected['pitch'])<1e-6
        for side in (-1,1):
            eye = bpy.data.objects[f'EyeAperture_{side}']
            assert abs(eye.scale.z-1)<1e-6, 'Eyeball must not be squashed to close eyes'
            iris = bpy.data.objects[f'Iris_{side}']
            assert abs(iris.location.x-expected['gaze_x']*0.012)<1e-6
            assert abs(iris.location.z-expected['gaze_y']*0.009)<1e-6
            for upper in ('Upper','Lower'):
                obj = bpy.data.objects[f'Eyelid_{upper}_{side}']
                for step in range(1,5):
                    name = 'Close' if step==4 else f'Close{step*25}'
                    value = obj.data.shape_keys.key_blocks[name].value
                    assert abs(value-max(0,1-abs(expected['eye_close']*4-step)))<1e-6
                if expected['eye_close']>0.999:
                    # Actual closed-shell boundary reaches across the eye centre.
                    key = obj.data.shape_keys.key_blocks['Close']
                    boundary = key.data[-33:]
                    assert all(v.co.z<0 if upper=='Upper' else v.co.z>0 for v in boundary)
        for name in ('MouthLips','MouthInterior'):
            keys = bpy.data.objects[name].data.shape_keys.key_blocks
            assert abs(keys['A'].value-expected['mouth_open'])<1e-6
            assert abs(keys['Smile'].value-expected['smile']*(1-0.8*expected['mouth_open']))<1e-6
        jaw = bpy.data.objects['Head'].data.shape_keys.key_blocks['JawOpen'].value
        assert abs(jaw-expected['mouth_open']*0.85)<1e-6
    assert all(abs(v)<1e-6 for v in sample_plan(plan,(scene.frame_end-1)/fps).values())
    required = {'eye_close':'eye_close','gaze':'gaze_x','smile':'smile','mouth_open':'mouth_open','nod':'pitch'}
    if case['name'] in required:
        assert extrema[required[case['name']]]>0.1
        allowed = {'gaze_x','gaze_y'} if case['name']=='gaze' else {required[case['name']]}
        assert all(v==0 for k,v in extrema.items() if k not in allowed)
    else:
        assert all(extrema[k]>0.1 for k in ('eye_close','gaze_x','smile','mouth_open','pitch'))
    results.append(dict(name=case['name'],baked_frames_checked=scene.frame_end,extrema=extrema,passed=True))
(path.parent/'baked-checks.json').write_text(json.dumps(results,indent=2),'utf-8')
print('BAKED FIVE CONTROLS VALIDATED',len(results))

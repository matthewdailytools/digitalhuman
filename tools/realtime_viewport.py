"""Persistent native Blender viewport. No video rendering, no listening network port."""
import argparse
from collections import deque
import json
import math
from pathlib import Path
import sys
import time
import traceback

import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from realtime_preview import CHANNELS,validate_state,atomic_json,read_json,try_atomic_json,HeartbeatWatch
from micro_control import sample_plan
from smile_sample import smile_plan

parser=argparse.ArgumentParser();parser.add_argument('--session',required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);folder=Path(args.session).resolve()
session=json.loads((folder/'session.json').read_text('utf-8'))
bpy.ops.wm.open_mainfile(filepath=session['rig_file'],load_ui=False,use_scripts=False)
scene=bpy.context.scene;rig=bpy.data.objects['ScanRig']
if rig.animation_data:rig.animation_data.action=None
for name in CHANNELS:rig[name]=0.0
for obj in scene.objects:
    if obj.type=='MESH':
        for modifier in obj.modifiers:
            if modifier.type=='SUBSURF':modifier.levels=min(1,modifier.levels)
    obj.select_set(False)
    if obj.type=='MESH':
        for mat in obj.data.materials:
            if not mat or not mat.use_nodes:continue
            textures=[n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image]
            diffuse=next((n for n in textures if any(word in n.image.name.lower() for word in ('albedo','diffuse'))),None)
            if diffuse:mat.node_tree.nodes.active=diffuse
rig.hide_set(True)
bpy.data.objects['ScalpSurface'].hide_set(True)
# A viewport-only hair approximation; keep the cached production materials untouched.
hair=bpy.data.objects['ShortHair'];material=bpy.data.materials.new('Realtime hair approximation');material.diffuse_color=(.055,.025,.012,1)
material.use_nodes=True;shader=material.node_tree.nodes.get('Principled BSDF')
shader.inputs['Base Color'].default_value=material.diffuse_color;shader.inputs['Roughness'].default_value=.65
hair.data.materials.clear();hair.data.materials.append(material)
scene.render.engine='BLENDER_EEVEE_NEXT';scene.render.resolution_percentage=100
scene.render.film_transparent=False
eevee=getattr(scene,'eevee',None)
if hasattr(eevee,'taa_samples'):eevee.taa_samples=8
if hasattr(eevee,'use_raytracing'):eevee.use_raytracing=False
for light in (o for o in scene.objects if o.type=='LIGHT'):
    light.hide_set(False)
camera=bpy.data.objects['Baseline_front'];camera.data.sensor_fit='VERTICAL';camera.data.sensor_height=36
target=Vector((0,-2,24));camera.location=target+Vector((0,-96,1.5))
camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();scene.camera=camera
scene.render.resolution_x=512;scene.render.resolution_y=640

views=[]
for window in bpy.context.window_manager.windows:
    window.scene=scene
    for area in window.screen.areas:
        if area.type=='VIEW_3D':
            space=area.spaces.active;space.overlay.show_overlays=False;space.show_gizmo=False
            space.region_3d.view_perspective='CAMERA';space.region_3d.view_camera_zoom=18
            space.shading.type='SOLID';space.shading.light='STUDIO';space.shading.color_type='TEXTURE'
            space.shading.show_shadows=True;space.shading.show_cavity=True
            space.shading.background_type='WORLD';views.append((area,space))
if not views:raise RuntimeError('No native 3D viewport available')

target_state=dict.fromkeys(CHANNELS,0.0);current=target_state.copy()
last_seq=0;last_tick=time.perf_counter();last_status=0;sample_started=None;mode=None;capture_seq=None;capture_after=0
draw_times=deque(maxlen=120);apply_delay_ms=0;settled_ms=0;sent_at=0;active=False;ready_at=time.time()
heartbeat_watch=HeartbeatWatch(time.perf_counter())

def draw():
    if bpy.context.area!=views[0][0]:return
    draw_times.append(time.perf_counter())

handler=bpy.types.SpaceView3D.draw_handler_add(draw,(),'WINDOW','POST_PIXEL')

def tick():
    global last_seq,last_tick,last_status,sample_started,mode,capture_seq,capture_after,apply_delay_ms,settled_ms,sent_at,active,target_state
    now=time.perf_counter();dt=min(.25,max(0,now-last_tick));last_tick=now
    try:
        if (folder/'stop.json').exists():bpy.ops.wm.quit_blender();return None
        if not heartbeat_watch.alive(read_json(folder/'heartbeat.json'),now):bpy.ops.wm.quit_blender();return None
        command=read_json(folder/'command.json')
        new=False
        if command and command['seq']>last_seq:
            target_state=validate_state(command['controls']);last_seq=command['seq'];new=True
            sent_at=command['sent_at'];apply_delay_ms=max(0,(time.time()-sent_at)*1000);settled_ms=0
            sample_started=now if command.get('sample') else None
            wanted=command['mode']
            if wanted not in ('solid','eevee'):raise ValueError('Unsupported preview mode')
            if wanted!=mode:
                mode=wanted
                for area,space in views:space.shading.type='SOLID' if mode=='solid' else 'RENDERED'
                for obj in scene.objects:
                    if obj.type=='MESH':
                        for modifier in obj.modifiers:
                            if modifier.type=='SUBSURF':modifier.levels=0 if mode=='solid' else 1
                draw_times.clear()
                for name in ('Lens Left','Lens Right','Eye Wet'):
                    bpy.data.objects[name].hide_set(mode=='solid')
            hair.hide_set(not command['hair'])
            if command.get('capture'):
                capture_seq=last_seq;capture_after=now+(8 if mode=='eevee' else 2)
        if sample_started is not None:
            elapsed=now-sample_started
            if elapsed>6:sample_started=None;target_state=dict.fromkeys(CHANNELS,0.0)
            else:
                state=sample_plan(smile_plan(),elapsed);state['nod']=state.pop('pitch')/math.radians(12);target_state=state
        maximum=max(abs(current[k]-target_state[k]) for k in CHANNELS)
        active=maximum>1e-4 or sample_started is not None
        if new or active:
            weight=1-math.exp(-dt/.055)
            for name in CHANNELS:
                delta=target_state[name]-current[name]
                current[name]=target_state[name] if abs(delta)<1e-4 else current[name]+delta*weight
                rig[name]=current[name]
            rig.update_tag();bpy.context.view_layer.update()
        if maximum<.005 and settled_ms==0 and sent_at:settled_ms=max(0,(time.time()-sent_at)*1000)
        if new or active or capture_seq is not None:
            for area,space in views:area.tag_redraw()
        if capture_seq is not None and now>=capture_after and not active:
            # POST_PIXEL can expose only the overlay buffer on this Intel driver.
            # Capture the viewport through Blender's own GPU viewport operator instead.
            destination=folder/('viewport-'+str(capture_seq)+'.png');temporary=folder/('capture-'+str(capture_seq)+'.tmp.png')
            scene.render.filepath=str(temporary)
            window=bpy.context.window_manager.windows[0];area=views[0][0]
            region=next(r for r in area.regions if r.type=='WINDOW')
            with bpy.context.temp_override(window=window,area=area,region=region):
                bpy.ops.render.opengl(write_still=True,view_context=True)
            temporary.replace(destination);capture_seq=None
        if now-last_status>.2 or new:
            import gpu
            intervals=[b-a for a,b in zip(draw_times,list(draw_times)[1:]) if 0<b-a<1]
            keys=bpy.data.objects['Head'].data.shape_keys.key_blocks
            written=try_atomic_json(folder/'status.json',dict(phase='ready',pid=__import__('os').getpid(),seq=last_seq,mode=mode,
                        controls={k:rig[k] for k in CHANNELS},target=target_state,
                        shape_values={k:keys[k].value for k in ('EyeClose','SmileCorners','SmileCheeks','SmileLids','SmileOpenCorrective')},
                        jaw_angle=rig.pose.bones['Jaw'].rotation_euler.x,active=active,
                        hair_visible=not hair.hide_get(),hair_strands=len(hair.data.curves),
                        rig_sha256=session['rig_sha256'],
                        sample_playing=sample_started is not None,
                        head_angle=rig.pose.bones['Head'].rotation_euler.x,
                        neck_angle=rig.pose.bones['Neck'].rotation_euler.x,
                        eye_angles=list(bpy.data.objects['EyePivot_Left'].rotation_euler),
                        apply_delay_ms=apply_delay_ms,settled_ms=settled_ms,
                        viewport_draw_fps=(len(intervals)/sum(intervals) if intervals else 0),draw_count=len(draw_times),
                        gpu=gpu.platform.renderer_get(),ready_at=ready_at))
            if written:last_status=now
        return 1/30
    except Exception:
        error=traceback.format_exc();(folder/'error.log').write_text(error,'utf-8')
        atomic_json(folder/'status.json',dict(phase='failed',error=error));return None

bpy.app.timers.register(tick,first_interval=.5)

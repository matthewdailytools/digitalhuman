"""Load the vendor scene, adapt a separate copy, and render three fixed reference views."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

parser=argparse.ArgumentParser()
parser.add_argument('--original',required=True)
parser.add_argument('--textures',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--samples',type=int,default=64)
parser.add_argument('--width',type=int,default=768)
parser.add_argument('--height',type=int,default=960)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
original,output=Path(args.original).resolve(),Path(args.output).resolve()
output.mkdir(parents=True,exist_ok=True)
source=original/'Blender/Blender Scene.blend'
if output.is_relative_to(original):raise ValueError('Render output must not replace the original asset')
textures=json.loads(Path(args.textures).read_text('utf-8'))
proxies={row['name']:row for row in textures['entries']}
bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=False)
scene=bpy.context.scene
original_settings=dict(camera=scene.camera.name,engine=scene.render.engine,samples=scene.cycles.samples,
                       device=scene.cycles.device,resolution=[scene.render.resolution_x,scene.render.resolution_y])
resolved=[]
for image in bpy.data.images:
    if image.source!='FILE':continue
    name=Path(image.filepath.replace(chr(92),'/')).name
    row=proxies.get(name)
    if row:
        path=Path(row['proxy'])
        with path.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=row['proxy_sha256']:
                raise ValueError('Texture proxy checksum mismatch')
    elif name=='HDRI.exr':path=original/'Blender/HDRI.exr'
    else:raise ValueError('Unresolved original texture: '+name)
    if not path.is_file():raise ValueError('Missing texture: '+name)
    image.filepath=str(path)
    image.reload()
    resolved.append(dict(name=image.name,path=str(path),colorspace=image.colorspace_settings.name))
scene.render.engine='CYCLES'
scene.cycles.device='CPU'
scene.render.threads_mode='FIXED';scene.render.threads=4
scene.cycles.samples=args.samples
scene.cycles.use_denoising=True
scene.cycles.use_adaptive_sampling=True
scene.cycles.adaptive_threshold=0.03
scene.cycles.seed=17
scene.cycles.use_animated_seed=False
scene.cycles.max_bounces=8
scene.cycles.diffuse_bounces=3
scene.cycles.glossy_bounces=4
scene.cycles.transmission_bounces=6
scene.render.use_persistent_data=False
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.image_settings.color_mode='RGB'
scene.render.image_settings.color_depth='8'
scene.render.film_transparent=False
scene.render.use_compositing=False
scene.render.use_sequencer=False
scene.render.use_simplify=True
scene.render.simplify_subdivision=1
scene.render.simplify_subdivision_render=2
scene.cycles.texture_limit='2048'
scene.cycles.texture_limit_render='2048'
for obj in scene.objects:
    for modifier in obj.modifiers:
        if modifier.type=='SUBSURF':
            modifier.levels=1 if obj.name=='Head' else 0
            modifier.render_levels=2 if obj.name=='Head' else (0 if obj.name in ('Brows','Lashes') else 1)
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.shading.type='SOLID'
            area.spaces.active.region_3d.view_perspective='CAMERA'
report=dict(source=str(source),original_settings=original_settings,blender=bpy.app.version_string,
            renderer='CYCLES CPU',threads=4,samples=args.samples,texture_maximum=textures['maximum'],
            resolved_images=resolved,source_materials_preserved=True,views=[])
# Preserve the supplied camera and lighting for an inexpensive compatibility reference.
scene.render.resolution_x=640;scene.render.resolution_y=278
scene.cycles.samples=32
scene.camera=bpy.data.objects[original_settings['camera']]
scene.camera.data.dof.use_dof=False
scene.render.filepath=str(output/'vendor-camera-preview.png')
started=time.monotonic();bpy.ops.render.render(write_still=True)
report['vendor_reference']=dict(path=scene.render.filepath,seconds=time.monotonic()-started,
                                note='Vendor camera/materials/lighting; CPU, 2K proxy textures, lower subdivision and sampling')
scene.render.resolution_x=args.width;scene.render.resolution_y=args.height
scene.cycles.samples=args.samples
head=bpy.data.objects['Head']
# The vendor scene is in centimetres. Keep the actual mesh and its transforms unchanged.
target=Vector((0,-2,23.2))
radius=91.0
cameras={}
for name,degrees in (('front',0),('left',-45),('right',45)):
    camera_data=bpy.data.cameras.new('Baseline_'+name)
    camera=bpy.data.objects.new('Baseline_'+name,camera_data)
    scene.collection.objects.link(camera)
    angle=math.radians(degrees)
    camera.location=target+Vector((radius*math.sin(angle),-radius*math.cos(angle),1.5))
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera_data.lens=70
    camera_data.sensor_width=36
    camera_data.clip_start=.1;camera_data.clip_end=1000
    camera_data.dof.use_dof=False
    cameras[name]=camera
    scene.camera=camera
    bpy.context.view_layer.update()
    bounds=[world_to_camera_view(scene,camera,head.matrix_world@Vector(p)) for p in head.bound_box]
    if not all(0<p.x<1 and 0<p.y<1 and p.z>0 for p in bounds):
        raise ValueError('Head is clipped in baseline camera '+name)
    scene.render.filepath=str(output/(name+'.png'))
    started=time.monotonic();bpy.ops.render.render(write_still=True)
    report['views'].append(dict(name=name,azimuth_degrees=degrees,path=scene.render.filepath,
                               seconds=time.monotonic()-started,camera_bounds_passed=True))
    print('BASELINE VIEW COMPLETE',name,flush=True)
scene.camera=cameras['front']
scene.render.filepath=str(output/'front.png')
scene['asset_source']='3D Scan Store Free HD Head'
scene['asset_license']='PERSONAL USE ONLY; contact vendor for commercial use'
scene['baseline_settings']=json.dumps(dict(samples=args.samples,textures=textures['maximum'],seed=17))
scene['no_facial_rig']=True
# Embed only the small proxy textures and HDRI, making the preview project portable locally.
bpy.ops.file.pack_all()
blend=output/'head-preview.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend),compress=True)
report['preview_blend']=str(blend)
report['success']=True
(output/'render-report.json').write_text(json.dumps(report,indent=2),'utf-8')
print('STATIC HEAD BASELINE COMPLETE',output,flush=True)

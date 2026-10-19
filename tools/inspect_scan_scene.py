"""Inspect a vendor Blender scene with embedded Python execution disabled."""
import argparse
import json
from pathlib import Path
import sys

import bpy

parser = argparse.ArgumentParser()
parser.add_argument('--blend', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
bpy.ops.wm.open_mainfile(filepath=str(Path(args.blend).resolve()), load_ui=False, use_scripts=False)
scene = bpy.context.scene
objects = []
for obj in scene.objects:
    info = dict(name=obj.name, type=obj.type, hide_render=obj.hide_render,
                location=list(obj.location), scale=list(obj.scale), rotation=list(obj.rotation_euler))
    if obj.type == 'MESH':
        info.update(vertices=len(obj.data.vertices), polygons=len(obj.data.polygons),
                    bounds=[list(obj.matrix_world @ __import__('mathutils').Vector(p)) for p in obj.bound_box],
                    materials=[m.name if m else None for m in obj.data.materials],
                    modifiers=[dict(name=m.name, type=m.type, show_render=m.show_render,
                                    levels=getattr(m,'levels',None), render_levels=getattr(m,'render_levels',None))
                               for m in obj.modifiers],
                    shape_keys=list(obj.data.shape_keys.key_blocks.keys()) if obj.data.shape_keys else [])
    if obj.type == 'LIGHT':
        info.update(light_type=obj.data.type, energy=obj.data.energy)
    if obj.type == 'CAMERA':
        info.update(lens=obj.data.lens, clip_start=obj.data.clip_start, clip_end=obj.data.clip_end)
    objects.append(info)
report = dict(blend=str(Path(args.blend).resolve()), blender=bpy.app.version_string,
              scene=scene.name, engine=scene.render.engine,
              resolution=[scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage],
              cycles_samples=scene.cycles.samples, cycles_device=scene.cycles.device,
              camera=scene.camera.name if scene.camera else None,
              color=dict(view_transform=scene.view_settings.view_transform,look=scene.view_settings.look,
                         exposure=scene.view_settings.exposure), objects=objects,
              images=[dict(name=i.name,filepath=i.filepath,size=list(i.size) if i.has_data else None,packed=bool(i.packed_file),
                           colorspace=i.colorspace_settings.name)
                      for i in bpy.data.images if i.source=='FILE'],
              materials=[dict(name=m.name,nodes=[dict(name=n.name,type=n.bl_idname)
                                                for n in m.node_tree.nodes] if m.use_nodes else [])
                         for m in bpy.data.materials])
output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(report,indent=2),'utf-8')
print('SCENE INSPECTED',len(objects),'objects;',len(report['images']),'images;',output)

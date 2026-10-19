"""Build a local, editable scan rig and short native hair curves in Blender 4.5."""
import bisect
import json
import math
from pathlib import Path
import random
import sys

import bpy
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scan_binding import (smooth,jaw_weights,blink_delta,hairline,
                          smile_corner_delta,smile_cheek_delta,smile_lid_delta,smile_open_delta)
from micro_control import sample_plan,validate_plan

CHANNELS=('eye_close','gaze_x','gaze_y','smile','mouth_open','nod')


def parent_bone(obj,rig,bone):
    world=obj.matrix_world.copy()
    obj.parent=rig;obj.parent_type='BONE';obj.parent_bone=bone
    bpy.context.view_layer.update();obj.matrix_world=world


def driver(owner,path,rig,expression,variables,index=None):
    curve=owner.driver_add(path) if index is None else owner.driver_add(path,index)
    drv=curve.driver;drv.type='SCRIPTED';drv.expression=expression
    for name,channel in variables.items():
        v=drv.variables.new();v.name=name;v.type='SINGLE_PROP'
        v.targets[0].id=rig;v.targets[0].data_path='["'+channel+'"]'
    return curve


def armature(obj,rig,weights):
    groups={name:obj.vertex_groups.new(name=name) for name in ('Root','Neck','Head','Jaw')}
    for index,values in enumerate(weights):
        for name,weight in values.items():
            if weight>1e-7:groups[name].add([index],weight,'REPLACE')
    modifier=obj.modifiers.new('Scan facial skeleton','ARMATURE');modifier.object=rig
    # Shape keys -> armature -> subdivision, preserving smooth deformations.
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.modifier_move_up(modifier=modifier.name)
    obj.parent=rig


def shape(obj,name,delta):
    if not obj.data.shape_keys:obj.shape_key_add(name='Basis')
    key=obj.shape_key_add(name=name)
    changed=0
    for vertex,point in zip(key.data,obj.data.vertices):
        d=Vector(delta(point.co))
        vertex.co=point.co+d
        changed+=d.length>1e-7
    return key,changed


def build_hair(head,rig,landmarks):
    vertices=[];faces=[];uvs=[];coverage=[];mapping={}
    uv=head.data.uv_layers.active
    for poly in head.data.polygons:
        points=[head.data.vertices[i].co for i in poly.vertices]
        if not all(p.z>hairline(p.x,p.y)-.25 and abs(p.x)<9.6 for p in points):continue
        indices=[];face_uv=[]
        for vi,li in zip(poly.vertices,poly.loop_indices):
            if vi not in mapping:
                source=head.data.vertices[vi];p=source.co+source.normal*.025
                mapping[vi]=len(vertices);vertices.append(tuple(p))
                coverage.append(smooth(-.1,.9,p.z-hairline(p.x,p.y)))
            indices.append(mapping[vi]);face_uv.append(tuple(uv.data[li].uv))
        faces.append(indices);uvs.append(face_uv)
    mesh=bpy.data.meshes.new('ScalpSurface');mesh.from_pydata(vertices,[],faces);mesh.update()
    scalp=bpy.data.objects.new('ScalpSurface',mesh);bpy.context.scene.collection.objects.link(scalp)
    layer=mesh.uv_layers.new(name='UVMap')
    for poly,values in zip(mesh.polygons,uvs):
        poly.use_smooth=True
        for loop,value in zip(poly.loop_indices,values):layer.data[loop].uv=value
    attr=mesh.attributes.new('HairDensity','FLOAT','POINT')
    attr.data.foreach_set('value',coverage)
    material=bpy.data.materials.new('ShortHair scalp fade');material.use_nodes=True
    nodes=material.node_tree.nodes;nodes.clear();links=material.node_tree.links
    output=nodes.new('ShaderNodeOutputMaterial');mix=nodes.new('ShaderNodeMixShader')
    transparent=nodes.new('ShaderNodeBsdfTransparent');base=nodes.new('ShaderNodeBsdfPrincipled')
    base.inputs['Base Color'].default_value=(.018,.008,.004,1);base.inputs['Roughness'].default_value=.62
    attribute=nodes.new('ShaderNodeAttribute');attribute.attribute_name='HairDensity'
    links.new(attribute.outputs['Fac'],mix.inputs[0]);links.new(transparent.outputs[0],mix.inputs[1])
    links.new(base.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],output.inputs[0]);mesh.materials.append(material)
    mesh.calc_loop_triangles();triangles=list(mesh.loop_triangles)
    cumulative=[];total=0
    for triangle in triangles:total+=triangle.area;cumulative.append(total)
    rng=random.Random(landmarks['hair_seed']);count=landmarks['hair_strands'];steps=landmarks['hair_points']
    positions=[];radii=[];anchors=[];roots=[]
    for strand in range(count):
        triangle=triangles[bisect.bisect_left(cumulative,rng.random()*total)]
        a,b,c=[mesh.vertices[i].co for i in triangle.vertices]
        t=math.sqrt(rng.random());u=rng.random();weights=(1-t,t*(1-u),t*u)
        p=a*weights[0]+b*weights[1]+c*weights[2]
        normal=sum((mesh.vertices[i].normal*w for i,w in zip(triangle.vertices,weights)),Vector()).normalized()
        density=smooth(-.2,.9,p.z-hairline(p.x,p.y))
        top=smooth(33,38,p.z)
        direction=Vector((.9*top,.10*(1-top)-.35*top,-1*(1-top)))
        tangent=(direction-normal*direction.dot(normal)).normalized()
        cross=normal.cross(tangent).normalized()
        length=(.85+2.9*top)*rng.uniform(.7,1.2)*(.45+.55*density)
        lift=(.10+1.0*top)*rng.uniform(.8,1.3)
        phase=rng.random()*math.tau
        for index in range(steps):
            s=index/(steps-1)
            point=p+normal*(.02+lift*math.sin(s*math.pi/2)*(1-.35*s))+tangent*length*s
            point+=cross*(.025*math.sin(s*math.tau+phase)*s)
            positions.extend(point)
            radii.append(.0085*rng.uniform(.9,1.1)*max(.08,(1-s)**.65))
        triangle_uv=[layer.data[i].uv for i in triangle.loops]
        anchors.extend(sum((value*w for value,w in zip(triangle_uv,weights)),Vector((0,0))))
        roots.append(tuple(p))
    curves=bpy.data.hair_curves.new('ShortHair strands')
    curves.add_curves([steps]*count)
    curves.attributes['position'].data.foreach_set('vector',positions)
    curves.attributes.new('radius','FLOAT','POINT').data.foreach_set('value',radii)
    curves.attributes.new('surface_uv_coordinate','FLOAT2','CURVE').data.foreach_set('vector',anchors)
    curves.surface=scalp;curves.surface_uv_map='UVMap'
    hair=bpy.data.objects.new('ShortHair',curves);bpy.context.scene.collection.objects.link(hair)
    hair_material=bpy.data.materials.new('ShortHair dark brown');hair_material.use_nodes=True
    nodes=hair_material.node_tree.nodes;nodes.clear();links=hair_material.node_tree.links
    output=nodes.new('ShaderNodeOutputMaterial');shader=nodes.new('ShaderNodeBsdfHairPrincipled')
    shader.parametrization='MELANIN'
    for name,value in (('Melanin',.78),('Melanin Redness',.25),('Roughness',.38),('Radial Roughness',.45),('Random Color',.12)):
        if name in shader.inputs:shader.inputs[name].default_value=value
    if 'Random' in shader.inputs:
        info=nodes.new('ShaderNodeHairInfo');links.new(info.outputs['Random'],shader.inputs['Random'])
    links.new(shader.outputs[0],output.inputs[0]);curves.materials.append(hair_material)
    armature(scalp,rig,[{'Head':1} for _ in mesh.vertices])
    parent_bone(hair,rig,'Head')
    scalp.hide_render=True  # Keep the editable scalp anchor, render actual strands instead of a helmet shell.
    hair['binding']='Head bone; scalp UV anchors for grooming; no physics'
    return dict(strands=count,points=steps,surface=scalp.name,head_bone_attached=True,
                root_bounds=[[min(p[k] for p in roots),max(p[k] for p in roots)] for k in range(3)])


def build(hair=True):
    landmarks=json.loads((ROOT/'configs/scanned-head-landmarks.json').read_text('utf-8'))
    scene=bpy.context.scene;head=bpy.data.objects['Head']
    if len(head.data.vertices)!=landmarks['vertex_count']:raise ValueError('Scan topology mismatch')
    for obj in list(scene.objects):
        if obj.type=='MESH':
            obj.data.transform(obj.matrix_world);obj.matrix_world=Matrix.Identity(4);obj.data.update()
    data=bpy.data.armatures.new('ScanSkeleton');rig=bpy.data.objects.new('ScanRig',data)
    scene.collection.objects.link(rig);bpy.context.view_layer.objects.active=rig;rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for name,start,end,parent in (
        ('Root',(0,0,5),(0,0,10),None),('Neck',(0,-1,14),(0,-1,18),'Root'),
        ('Head',landmarks['head_pivot'],(0,-1,30),'Neck'),('Jaw',landmarks['jaw_pivot'],(0,-12,21),'Head')):
        bone=data.edit_bones.new(name);bone.head=start;bone.tail=end
        if parent:bone.parent=data.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT');rig.show_in_front=True
    # Use world-aligned bone X as the pitch axis, including the diagonal jaw bone.
    for bone in rig.pose.bones:bone.rotation_mode='XYZ'
    for channel in CHANNELS:
        rig[channel]=0.0;rig.id_properties_ui(channel).update(min=-1 if channel.startswith('gaze') else 0,max=1)
    points=[tuple(v.co) for v in head.data.vertices];faces=[list(p.vertices) for p in head.data.polygons]
    jaw=jaw_weights(points,faces,landmarks['upper_lip_seed'],landmarks['lower_lip_seed'])
    weights=[]
    for p,jw in zip(points,jaw):
        neck=smooth(10.5,16,p[2]);upper=smooth(14,19,p[2]);h=neck*upper
        weights.append({'Root':1-neck,'Neck':neck*(1-upper),'Head':h*(1-jw),'Jaw':h*jw})
    armature(head,rig,weights)
    counts={}
    for name in ('Head','Lashes','Eye Wet'):
        obj=bpy.data.objects[name]
        key,changed=shape(obj,'EyeClose',lambda p:blink_delta(p,landmarks['eye_centers']))
        driver(key,'value',rig,'v',{'v':'eye_close'});counts[name]=changed
        key,changed=shape(obj,'SmileLids',lambda p:smile_lid_delta(p,landmarks['eye_centers']))
        driver(key,'value',rig,'s*(1-b)',{'s':'smile','b':'eye_close'});counts[name+'_SmileLids']=changed
        if name!='Head':armature(obj,rig,[{'Head':1} for _ in obj.data.vertices])
    for name,delta in (('SmileCorners',smile_corner_delta),('SmileCheeks',smile_cheek_delta)):
        key,changed=shape(head,name,delta)
        driver(key,'value',rig,'s',{'s':'smile'});counts[name]=changed
    key,changed=shape(head,'SmileOpenCorrective',smile_open_delta)
    driver(key,'value',rig,'s*m',{'s':'smile','m':'mouth_open'});counts['SmileOpenCorrective']=changed
    rig['smile_style']='friendly-v2: corners + cheek volume + mild eyelid narrowing; explicit blink overrides lids'
    armature(bpy.data.objects['Brows'],rig,[{'Head':1} for _ in bpy.data.objects['Brows'].data.vertices])
    teeth=bpy.data.objects['Teeth']
    # Separate tooth/gum islands before assigning upper/lower jaw; never split a tooth by height.
    adj=[set() for _ in teeth.data.vertices]
    for face in teeth.data.polygons:
        ids=list(face.vertices)
        for a,b in zip(ids,ids[1:]+ids[:1]):adj[a].add(b);adj[b].add(a)
    todo=set(range(len(adj)));tw=[None]*len(adj);islands=[]
    while todo:
        stack=[todo.pop()];ids=[]
        while stack:
            i=stack.pop();ids.append(i)
            for j in adj[i]&todo:todo.remove(j);stack.append(j)
        cz=sum(teeth.data.vertices[i].co.z for i in ids)/len(ids)
        bone='Jaw' if cz<23.55 else 'Head'
        for i in ids:tw[i]={bone:1}
        islands.append(dict(vertices=len(ids),center_z=cz,bone=bone))
    armature(teeth,rig,tw)
    armature(bpy.data.objects['Tongue'],rig,[{'Jaw':1} for _ in bpy.data.objects['Tongue'].data.vertices])
    driver(rig.pose.bones['Jaw'],'rotation_euler',rig,'.26*v',{'v':'mouth_open'},0)
    driver(rig.pose.bones['Head'],'rotation_euler',rig,str(math.radians(10.8))+'*v',{'v':'nod'},0)
    driver(rig.pose.bones['Neck'],'rotation_euler',rig,str(math.radians(1.2))+'*v',{'v':'nod'},0)
    for side,center in zip(('Left','Right'),landmarks['eye_centers']):
        anchor=bpy.data.objects.new('EyeAnchor_'+side,None);scene.collection.objects.link(anchor)
        anchor.matrix_world=Matrix.Translation(Vector(center));bpy.context.view_layer.update()
        parent_bone(anchor,rig,'Head')
        pivot=bpy.data.objects.new('EyePivot_'+side,None);scene.collection.objects.link(pivot)
        pivot.parent=anchor;pivot.matrix_parent_inverse=Matrix.Identity(4);pivot.matrix_basis=Matrix.Identity(4)
        bpy.context.view_layer.update()
        for name in ('Realtime Eyeball '+side,'Lens '+side):
            obj=bpy.data.objects[name];world=obj.matrix_world.copy();obj.parent=pivot
            obj.matrix_parent_inverse=pivot.matrix_world.inverted();obj.matrix_world=world
        driver(pivot,'rotation_euler',rig,'-.16*v',{'v':'gaze_y'},0)
        driver(pivot,'rotation_euler',rig,'.24*v',{'v':'gaze_x'},2)
    report=dict(changed_vertices=counts,upper_lip_weight=jaw[landmarks['upper_lip_rim']],
                lower_lip_weight=jaw[landmarks['lower_lip_rim']],tooth_islands=islands,
                hair=build_hair(head,rig,landmarks) if hair else None)
    if report['upper_lip_weight']>.01 or report['lower_lip_weight']<.99:
        raise ValueError('Anatomical lip separation failed')
    scene['no_facial_rig']=False;scene['scan_rig_revision']='smile-v2';scene['scan_rig_report']=json.dumps(report)
    rig['controls_help']='eye_close / gaze_x / gaze_y / smile / mouth_open / nod; safe simple drivers'
    bpy.context.view_layer.objects.active=rig
    for obj in bpy.context.selected_objects:obj.select_set(False)
    rig.select_set(True)
    return rig,report


def animate(rig,plan,fps,frames):
    validate_plan(plan);scene=bpy.context.scene;scene.render.fps=fps
    scene.frame_start=1;scene.frame_end=frames
    for frame in range(1,frames+1):
        state=sample_plan(plan,(frame-1)/fps)
        state['nod']=state.pop('pitch')/math.radians(12)
        for channel in CHANNELS:
            rig[channel]=state[channel];rig.keyframe_insert(data_path='["'+channel+'"]',frame=frame)
    for curve in rig.animation_data.action.fcurves:
        for key in curve.keyframe_points:key.interpolation='LINEAR'
    scene['micro_control_plan']=json.dumps(plan)
    scene.frame_set(1);rig.update_tag();bpy.context.view_layer.update()

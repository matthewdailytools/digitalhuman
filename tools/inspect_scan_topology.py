"""Export neutral head topology and boundary loops for deterministic facial binding."""
import json
from pathlib import Path
import sys
from collections import Counter,defaultdict
import bpy
from mathutils import Vector

root=Path(__file__).resolve().parents[1]
latest=json.loads((root/'work/realistic-head/latest.json').read_text('utf-8'))
bpy.ops.wm.open_mainfile(filepath=latest['media']['head-preview.blend'],load_ui=False,use_scripts=False)
obj=bpy.data.objects['Head']
vertices=[list(obj.matrix_world@v.co) for v in obj.data.vertices]
faces=[list(p.vertices) for p in obj.data.polygons]
edges=Counter(tuple(sorted((a,b))) for face in faces for a,b in zip(face,face[1:]+face[:1]))
adj=defaultdict(set)
for (a,b),count in edges.items():
    if count==1:adj[a].add(b);adj[b].add(a)
todo=set(adj);loops=[]
while todo:
    pending=[todo.pop()];ids=[]
    while pending:
        i=pending.pop();ids.append(i)
        for j in adj[i]&todo:todo.remove(j);pending.append(j)
    pts=[Vector(vertices[i]) for i in ids]
    loops.append(dict(ids=ids,count=len(ids),center=list(sum(pts,Vector())/len(pts)),
                      minimum=[min(p[k] for p in pts) for k in range(3)],maximum=[max(p[k] for p in pts) for k in range(3)]))
report=dict(vertices=vertices,faces=faces,boundaries=loops,objects={})
for name in ('Head','Lashes','Brows','Realtime Eyeball Left','Realtime Eyeball Right','Lens Left','Lens Right','Teeth','Tongue'):
    o=bpy.data.objects[name]
    bounds=[o.matrix_world@Vector(p) for p in o.bound_box]
    report['objects'][name]=dict(center=list(sum(bounds,Vector())/8),bounds=[list(p) for p in bounds])
out=root/'work/scanned-head/topology.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report),'utf-8')
print(json.dumps({'boundaries':[{k:v for k,v in x.items() if k!='ids'} for x in loops], 'objects':{k:v['center'] for k,v in report['objects'].items()}},indent=2))

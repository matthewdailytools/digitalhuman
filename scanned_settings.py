"""Separate scan renderer contract, preserving the procedural renderer/cache behavior."""
import copy
import hashlib
import json
from pathlib import Path

from micro_control import validate_plan
from render_settings import PROJECT,sha256,tool_paths

GENERATOR='scanned-blender-v1'


def base_config(quality):
    if not isinstance(quality,dict) or set(quality)-{'profile','width','height','fps','samples','hair','camera'}:
        raise ValueError('无效写实画质字段')
    profile=quality.get('profile','draft')
    q=dict(profile=profile,width=640,height=360,fps=24,samples=4,hair='static',skin='scan-pbr',body='bust')
    if profile=='preview':q.update(width=960,height=540,samples=16)
    q.update({k:v for k,v in quality.items() if k!='camera'})
    config=dict(schema_version=1,character=dict(id='scanned-head',revision='v1'),
                scene=dict(revision='v1',camera=quality.get('camera','head-closeup'),lighting='scan-hdri-v1'),
                quality=q,performance=dict(text='',expression='neutral-with-blink',motion_revision='still',frames=2),
                generator=dict(id=GENERATOR,revision='v1'))
    validate(config)
    return config


def validate(config):
    sections={'schema_version','character','scene','quality','performance','generator'}
    if not isinstance(config,dict) or set(config)!=sections or type(config['schema_version']) is not int or config['schema_version']!=1:
        raise ValueError('无效写实渲染配置')
    allowed=dict(character={'id','revision','rig_file','rig_sha256','rig_key'},
                 scene={'revision','camera','lighting'},quality={'profile','width','height','fps','samples','hair','skin','body'},
                 performance={'text','expression','motion_revision','frames','micro_control'},
                 generator={'id','revision','resolved_signature'})
    for section,keys in allowed.items():
        if not isinstance(config[section],dict) or set(config[section])-keys:raise ValueError('无效写实配置字段：'+section)
    if config['character'].get('id')!='scanned-head' or config['character'].get('revision')!='v1':raise ValueError('写实角色版本无效')
    if config['generator'].get('id')!=GENERATOR or config['generator'].get('revision')!='v1':raise ValueError('写实后端版本无效')
    scene=config['scene'];q=config['quality'];p=config['performance']
    if scene.get('revision')!='v1' or scene.get('lighting')!='scan-hdri-v1' or scene.get('camera') not in ('head-closeup','fixed-half-body'):
        raise ValueError('写实镜头或灯光无效')
    if q.get('profile') not in ('draft','preview') or q.get('skin')!='scan-pbr' or q.get('body')!='bust':raise ValueError('写实质量档位无效')
    for name,lo,hi in (('width',128,1920),('height',128,1080),('fps',1,30),('samples',1,64)):
        if type(q.get(name)) is not int or not lo<=q[name]<=hi:raise ValueError('写实参数无效：'+name)
    if q['width']%2 or q['height']%2:raise ValueError('视频分辨率须为偶数')
    if q.get('hair') not in ('none','static'):raise ValueError('写实短发支持静态或关闭；尚未实现发丝物理，请选择静态头发')
    if p.get('text')!='' or p.get('expression')!='neutral-with-blink' or p.get('motion_revision')!='still':
        raise ValueError('写实入口目前只支持五项控制无对白视频')
    if type(p.get('frames')) is not int or not 2<=p['frames']<=q['fps']*30:raise ValueError('写实帧数无效')
    if 'micro_control' in p:
        plan=validate_plan(p['micro_control'])
        if plan['duration']>(p['frames']-1)/q['fps']+1e-7:raise ValueError('写实动作超出时间轴')


def resolve(config):
    config=copy.deepcopy(config);validate(config)
    from scanned_assets import ensure_rig
    asset=ensure_rig()
    config['character'].update({k:asset[k] for k in ('rig_file','rig_sha256','rig_key')})
    tools=tool_paths()
    identity=dict(rig=asset['rig_sha256'],scripts={name:sha256(PROJECT/name) for name in
                  ('scanned_settings.py','scanned_renderer.py','tools/render_scanned_motion.py','tools/scanned_rig.py','scan_binding.py','micro_control.py')},
                  tools={name:dict(path=tools[name],size=Path(tools[name]).stat().st_size,mtime_ns=Path(tools[name]).stat().st_mtime_ns)
                         for name in ('blender','ffmpeg','ffprobe')})
    config['generator']['resolved_signature']=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    return config

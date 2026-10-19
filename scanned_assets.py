"""Validated local rig assets; shared by desktop and offline scan rendering."""
import json
from pathlib import Path
import subprocess

from layer_cache import cached_layer
from render_settings import PROJECT,sha256,tool_paths


def ensure_rig():
    pointer=PROJECT/'work/realistic-head/latest.json'
    if not pointer.is_file():raise ValueError('请先完成写实静态头部基准')
    source=Path(json.loads(pointer.read_text('utf-8'))['media']['head-preview.blend']).resolve()
    if not source.is_relative_to((PROJECT/'.cache/static-head').resolve()) or not source.is_file():
        raise ValueError('写实静态资产不存在或不在本机资产缓存中')
    manifest=json.loads((source.parent/'manifest.json').read_text('utf-8'))
    landmarks=json.loads((PROJECT/'configs/scanned-head-landmarks.json').read_text('utf-8'))
    if (manifest['files']['head-preview.blend']!=sha256(source) or
        manifest['identity']['sources']['Blender/Blender Scene.blend']!=landmarks['source_blend_sha256']):
        raise ValueError('静态资产已改变，请重新生成或为新拓扑更新面部标记')
    tools=tool_paths();executable=Path(tools['blender'])
    identity=dict(asset='scanned-head-rig-v1',source_sha256=sha256(source),
                  scripts={name:sha256(PROJECT/name) for name in
                           ('tools/scanned_rig.py','tools/build_scanned_head.py','scan_binding.py','configs/scanned-head-landmarks.json')},
                  blender=dict(path=str(executable),size=executable.stat().st_size,mtime_ns=executable.stat().st_mtime_ns))
    def produce(stage):
        print('asset: building scanned facial rig and short hair',flush=True)
        command=[str(executable),'--background','--factory-startup','--disable-autoexec','--threads','4',
                 '--python-exit-code','1','--python',str(PROJECT/'tools/build_scanned_head.py'),'--',
                 '--source',str(source),'--output',str(stage)]
        with (stage/'build.log').open('w',encoding='utf-8') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300,
                           cwd=PROJECT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        report=json.loads((stage/'binding-report.json').read_text('utf-8'))
        if not report.get('safe_drivers_verified') or report['hair']['strands']<10000:
            raise ValueError('写实绑定或发型构建验证失败')
        if sha256(source)!=identity['source_sha256']:raise ValueError('构建时静态资产发生变化')
    folder,hit=cached_layer(PROJECT/'.cache/layers/scanned-rigs',identity,produce)
    path=folder/'scanned-head-rig.blend'
    result=dict(rig_file=str(path.resolve()),rig_sha256=sha256(path),rig_key=folder.name,asset_hit=hit)
    pointer=PROJECT/'work/scanned-head/rig.json';pointer.parent.mkdir(parents=True,exist_ok=True)
    pointer.write_text(json.dumps(result,indent=2),'utf-8')
    return result

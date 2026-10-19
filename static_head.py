"""Content-addressed static-head reference rendering, separate from the mannequin pipeline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from PIL import Image, ImageDraw, ImageFont, ImageStat

from render_settings import tool_paths
from tools.prepare_head_textures import prepare

PROJECT=Path(__file__).resolve().parent
ORIGINAL=PROJECT/'.cache/assets/3dscanstore/original'
FILES=('front.png','left.png','right.png','vendor-camera-preview.png','overview.png',
       'head-preview.blend','render-report.json')


def digest(path):
    path=Path(path)
    if path.suffix=='.py':
        return hashlib.sha256(path.read_text('utf-8-sig').encode()).hexdigest()
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def cached(folder,identity):
    try:
        manifest=json.loads((folder/'manifest.json').read_text('utf-8'))
        return (manifest['identity']==identity and set(manifest['files'])==set(FILES)
                and all((folder/name).is_file() and digest(folder/name)==manifest['files'][name]
                        for name in FILES))
    except (OSError,ValueError,KeyError,TypeError):
        return False


def overview(folder):
    canvas=Image.new('RGB',(3*384,528),'#18201e')
    draw=ImageDraw.Draw(canvas)
    font=ImageFont.load_default(size=20)
    for index,(name,label) in enumerate((('left','LEFT 45'),('front','FRONT'),('right','RIGHT 45'))):
        with Image.open(folder/(name+'.png')) as image:
            image.load()
            if image.size!=(768,960) or max(ImageStat.Stat(image).stddev)<5:
                raise ValueError('Invalid or blank baseline image: '+name)
            canvas.paste(image.resize((384,480),Image.Resampling.LANCZOS),(index*384,48))
        draw.text((index*384+14,13),label,font=font,fill='white')
    canvas.save(folder/'overview.png')


def run(samples=64,maximum=2048):
    original=ORIGINAL.resolve()
    sources=[original/'Blender/Blender Scene.blend',original/'Blender/HDRI.exr']
    sources+=sorted((original/'Textures/JPG').rglob('*.jpg'))
    if len(sources)<3 or any(not path.is_file() for path in sources):
        raise ValueError('Extract the complete original head package first')
    tools=tool_paths()
    executable=Path(tools['blender'])
    identity=dict(schema_version=1,asset='3dscanstore-free-head-personal-use',
                  sources={str(path.relative_to(original)).replace(chr(92),'/'):digest(path) for path in sources},
                  scripts={name:digest(PROJECT/name) for name in ('static_head.py','tools/render_scan_head.py','tools/prepare_head_textures.py')},
                  blender=dict(path=str(executable),size=executable.stat().st_size,mtime_ns=executable.stat().st_mtime_ns),
                  settings=dict(samples=samples,texture_maximum=maximum,width=768,height=960,threads=4,seed=17,
                                angles=[-45,0,45],engine='CYCLES CPU'))
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    folder=PROJECT/'.cache/static-head'/key
    hit=cached(folder,identity)
    started=time.monotonic()
    if not hit:
        job=PROJECT/'work/static-head-jobs'/uuid.uuid4().hex
        job.mkdir(parents=True,exist_ok=False)
        prepare(original,job/'textures',maximum)
        output=job/'render'
        command=[str(executable),'--background','--factory-startup','--disable-autoexec','--threads','4',
                 '--python-exit-code','1','--python',str(PROJECT/'tools/render_scan_head.py'),'--',
                 '--original',str(original),'--textures',str(job/'textures/textures.json'),
                 '--output',str(output),'--samples',str(samples)]
        print('STATIC HEAD JOB:',job,flush=True)
        with (job/'blender.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=PROJECT,
                                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            while process.poll() is None:
                time.sleep(5)
                print('STATIC HEAD RENDERING',round(time.monotonic()-started,1),'seconds',flush=True)
        if process.returncode:
            raise RuntimeError('Static head render failed; inspect '+str(job/'blender.log'))
        overview(output)
        report=json.loads((output/'render-report.json').read_text('utf-8'))
        if not report.get('success') or len(report.get('views',[]))!=3:
            raise ValueError('Incomplete baseline render report')
        staging=folder.with_name(key+'.staging-'+uuid.uuid4().hex)
        staging.mkdir(parents=True,exist_ok=False)
        for name in FILES:
            shutil.copy2(output/name,staging/name)
        manifest=dict(identity=identity,files={name:digest(staging/name) for name in FILES},
                      license='Personal use only; contact 3D Scan Store for commercial use',job=str(job))
        (staging/'manifest.json').write_text(json.dumps(manifest,indent=2),'utf-8')
        if not cached(staging,identity):raise ValueError('Baseline cache verification failed')
        if folder.exists():folder.rename(folder.with_name(key+'.previous-'+uuid.uuid4().hex))
        staging.rename(folder)
    else:
        print('STATIC HEAD CACHE HIT: Blender and texture generation skipped',flush=True)
    result=dict(success=True,cache_hit=hit,cache_key=key,seconds=time.monotonic()-started,
                media={name:str((folder/name).resolve()) for name in FILES},
                license='Personal use only; commercial use requires vendor authorization')
    latest=PROJECT/'work/realistic-head/latest.json'
    latest.parent.mkdir(parents=True,exist_ok=True)
    temporary=latest.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    os.replace(temporary,latest)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--samples',type=int,choices=(32,64,128),default=64)
    parser.add_argument('--texture-maximum',type=int,choices=(1024,2048,4096),default=2048)
    args=parser.parse_args()
    try:run(args.samples,args.texture_maximum)
    except Exception as error:
        print('Static head task failed:',error,file=sys.stderr)
        sys.exit(1)

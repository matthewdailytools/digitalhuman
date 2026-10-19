"""Actual Blender + desktop backend + encoded video + blocked-render cache acceptance."""
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from desktop_controller import Jobs
from layer_cache import cached_layer
from micro_pipeline import run
from render_settings import tool_paths,sha256
from scanned_assets import ensure_rig
from tools.accept_scanned_head import check_blend,render_job

OUTPUT=ROOT/'work/smile-sample';OUTPUT.mkdir(parents=True,exist_ok=True)

def main():
    asset=ensure_rig();checks=check_blend(asset['rig_file'],OUTPUT/'rig-checks.json');tools=tool_paths()
    with (OUTPUT/'geometry.log').open('w',encoding='utf-8') as log:
        subprocess.run([tools['blender'],'--background','--factory-startup','--disable-autoexec','--threads','4',
                        '--python-exit-code','1','--python',str(ROOT/'tools/verify_smile.py'),'--',
                        '--blend',asset['rig_file'],'--output',str(OUTPUT/'geometry.json')],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180,cwd=ROOT)
    print('SMILE GEOMETRY PASSED',flush=True)
    request=dict(mode='smile-sample',character='scanned-head',
                 quality=dict(profile='draft',width=384,height=480,fps=8,samples=8,hair='static',camera='head-closeup'))
    (OUTPUT/'request.json').write_text(json.dumps(request,indent=2),'utf-8')
    jobs=Jobs();jobs.start('micro',request=request);started=time.monotonic()
    while (job:=jobs.snapshot())['state']=='running':
        if time.monotonic()-started>1800:raise TimeoutError('Smile desktop acceptance timed out')
        time.sleep(5);print('SMILE DESKTOP',job['stage'],job['frames_done'],flush=True)
    if job['state']!='succeeded':raise ValueError('Smile desktop task failed: '+str(job))
    case=Path(job['output_dir']);answer=json.loads((case/'answer.json').read_text('utf-8'))
    actual=render_job(answer['config']);clip=check_blend(actual/'scene.blend',OUTPUT/'clip-checks.json')
    assert clip['clip_frames_checked']==49
    with (patch('micro_pipeline.generate',side_effect=AssertionError('Repeat attempted rendering')),
          patch('ai_motion.request_deepseek',side_effect=AssertionError('Sample attempted API call'))):
        repeated=run(request,OUTPUT/'repeat')
    assert str(repeated)==answer['media_path']
    assert json.loads((OUTPUT/'repeat/result.json').read_text('utf-8'))['video_hit']
    old=json.loads((ROOT/'work/scanned-head/acceptance/report.json').read_text('utf-8'))['rig']['rig_file']
    identity=dict(rig=asset['rig_sha256'],before=sha256(old),worker=sha256(ROOT/'tools/render_smile_review.py'))
    def produce(stage):
        with (stage/'render.log').open('w',encoding='utf-8') as log:
            subprocess.run([tools['blender'],'--background','--factory-startup','--disable-autoexec','--threads','4',
                            '--python-exit-code','1','--python',str(ROOT/'tools/render_smile_review.py'),'--',
                            '--rig',asset['rig_file'],'--before',old,'--output',str(stage)],
                           stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1200,cwd=ROOT)
        from PIL import Image,ImageDraw
        names=('neutral','light','smile','before-smile','open-smile','before-open','closed-smile','left-smile','right-smile')
        canvas=Image.new('RGB',(960,1296),'#18201e');draw=ImageDraw.Draw(canvas)
        for i,name in enumerate(names):
            with Image.open(stage/(name+'.png')) as source:thumb=source.resize((320,400))
            x=(i%3)*320;y=(i//3)*432
            draw.text((x+8,y+9),name,fill='white');canvas.paste(thumb,(x,y+32))
        canvas.save(stage/'overview.png')
    portraits,hit=cached_layer(ROOT/'.cache/layers/smile-review',identity,produce)
    report=dict(success=True,rig=asset,geometry=json.loads((OUTPUT/'geometry.json').read_text('utf-8')),
                rig_checks=checks,clip_checks=clip,media=answer['media_path'],render_job=str(actual),
                desktop_task_id=job['id'],video_cache_reuse=True,no_api_required=True,
                portraits=str(portraits),portraits_cache_hit=hit)
    (OUTPUT/'report.json').write_text(json.dumps(report,indent=2),'utf-8')
    print('SMILE ACCEPTANCE COMPLETE',json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()

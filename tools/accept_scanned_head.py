"""Real Blender acceptance: five isolated controls, combined motion, cached AI, and hair portraits."""
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ai_motion import plan_actions
from desktop_controller import Jobs
from layer_cache import cached_layer
from micro_pipeline import run
from render_settings import sha256,tool_paths
from scanned_assets import ensure_rig
from static_head import overview

OUTPUT=ROOT/'work/scanned-head/acceptance'


def check_blend(blend,target):
    tools=tool_paths()
    command=[tools['blender'],'--background','--factory-startup','--disable-autoexec','--threads','4',
             '--python-exit-code','1','--python',str(ROOT/'tools/verify_scanned_rig.py'),'--',
             '--blend',str(blend),'--output',str(target)]
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180,cwd=ROOT)
    if result.returncode:
        target.with_suffix('.log').write_text(result.stdout+result.stderr,'utf-8')
        raise ValueError('Evaluated rig validation failed: '+str(target.with_suffix('.log')))
    return json.loads(target.read_text('utf-8'))


def render_job(config):
    for path in (ROOT/'work/render-jobs').glob('*/config.json'):
        if json.loads(path.read_text('utf-8'))==config:
            report=path.parent/'report.json'
            if report.is_file() and json.loads(report.read_text('utf-8')).get('success'):return path.parent
    raise ValueError('Validated render job not found')


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True);asset=ensure_rig()
    checks=check_blend(asset['rig_file'],OUTPUT/'rig-checks.json')
    quality=dict(profile='draft',width=384,height=480,fps=8,samples=4,hair='static',camera='head-closeup')
    results=[]
    controls=('eye_close','gaze','smile','mouth_open','nod')
    for name in (*controls,'combined'):
        values=dict(eye_close=0,smile=0,mouth_open=0,nod=0);gaze=[0,0]
        if name=='gaze':gaze=[1,.6]
        elif name=='combined':values.update(eye_close=1,smile=.7,mouth_open=.7,nod=.7);gaze=[-.5,.3]
        else:values[name]=1
        request=dict(mode='manual',character='scanned-head',controls=values,gaze=gaze,
                     duration=2 if name=='combined' else 1,quality=quality)
        case=OUTPUT/name;case.mkdir(exist_ok=True)
        (case/'request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),'utf-8')
        media=run(request,case)
        answer=json.loads((case/'answer.json').read_text('utf-8'));job=render_job(answer['config'])
        verified=check_blend(job/'scene.blend',case/'evaluated-checks.json')
        with patch('micro_pipeline.generate',side_effect=AssertionError('Repeat attempted another render')):
            assert run(request,case)==media
        assert json.loads((case/'result.json').read_text('utf-8'))['video_hit']
        results.append(dict(name=name,media=str(media),job=str(job),frames_checked=verified['clip_frames_checked'],cache_reuse=True))
        print('SCAN ACCEPTED',name,flush=True)
    instruction='用5秒依次闭眼、看向画面左、微笑、张嘴，最后轻轻点头。'
    # Reuse the real DeepSeek plan already accepted in this project. This gate prevents new billing.
    with patch('ai_motion.request_deepseek',side_effect=AssertionError('Real AI plan is not cached; no new billable call made')):
        real,hit=plan_actions(instruction,ROOT/'.cache/layers/motion-plans','deepseek','deepseek-flash')
    assert hit and real['source']=='deepseek'
    request=dict(mode='ai',character='scanned-head',instruction=instruction,provider='deepseek',model='deepseek-flash',quality=quality)
    jobs=Jobs();jobs.start('micro',request=request);started=time.monotonic()
    while (job:=jobs.snapshot())['state']=='running':
        if time.monotonic()-started>1800:raise TimeoutError('Desktop scan task exceeded acceptance deadline')
        time.sleep(5);print('DESKTOP SCAN',job['stage'],job['frames_done'],flush=True)
    if job['state']!='succeeded':raise ValueError('Desktop real-AI scan task failed: '+str(job['id']))
    case=Path(job['output_dir']);answer=json.loads((case/'answer.json').read_text('utf-8'))
    source=json.loads((case/'result.json').read_text('utf-8'));assert source['source']=='deepseek' and source['plan_hit']
    actual=render_job(answer['config']);verified=check_blend(actual/'scene.blend',OUTPUT/'deepseek-evaluated-checks.json')
    repeat=OUTPUT/'deepseek-repeat';repeat.mkdir(exist_ok=True)
    with (patch('micro_pipeline.generate',side_effect=AssertionError('AI repeat attempted rendering')),
          patch('ai_motion.request_deepseek',side_effect=AssertionError('AI repeat attempted billing'))):
        run(request,repeat)
    assert json.loads((repeat/'result.json').read_text('utf-8'))['video_hit']
    results.append(dict(name='deepseek-cached-plan',media=answer['media_path'],job=str(actual),
                        frames_checked=verified['clip_frames_checked'],cache_reuse=True,desktop_task_id=job['id']))
    identity=dict(asset=asset['rig_sha256'],script=sha256(ROOT/'tools/render_scanned_hero.py'),samples=48)
    def portraits(stage):
        tools=tool_paths()
        with (stage/'render.log').open('w',encoding='utf-8') as log:
            subprocess.run([tools['blender'],'--background','--factory-startup','--disable-autoexec','--threads','4',
                            '--python-exit-code','1','--python',str(ROOT/'tools/render_scanned_hero.py'),'--',
                            '--rig',asset['rig_file'],'--output',str(stage)],stdout=log,stderr=subprocess.STDOUT,
                            check=True,timeout=900,cwd=ROOT)
        overview(stage)
    hero,hero_hit=cached_layer(ROOT/'.cache/layers/scanned-portraits',identity,portraits)
    report=dict(success=True,rig=asset,rig_checks=checks,cases=results,
                total_clip_frames_checked=sum(x['frames_checked'] for x in results),
                portraits=str(hero),portraits_cache_hit=hero_hit,real_ai_plan_reused_without_new_billing=True,
                limitation='First procedural short haircut and five-control rig; no hair physics, TTS or production FACS set')
    (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('SCANNED HEAD ACCEPTANCE COMPLETE',json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()

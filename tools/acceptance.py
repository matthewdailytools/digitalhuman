"""Repeatable technical acceptance; subjective realism and phoneme accuracy remain manual."""
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import copy
import re

PROJECT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(PROJECT))
from cache_pipeline import cache_key,lookup,generate
from render_settings import resolve
from quality_profiles import apply_profile
from text_pipeline import prepare_speech
from playback import prepare_reel
from layer_cache import key_lock
from behavior import channels

SENTENCES=['爸爸妈妈，你们好。','请稍等一下。','今天是二十五号。','欢迎使用AI助手。','你想喝水吗？','我们一起出发吧。','哦，原来如此。','谢谢你的帮助。','这个方案不错。','再见，明天见。']


def main():
    output=PROJECT/'work/acceptance';output.mkdir(parents=True,exist_ok=True)
    report=dict(schema_version=1,scope='technical mannequin; SAPI amplitude timing; no photoreal/phoneme pass claim',
                cases=[],success=False,external_api='not exercised by this offline suite; use deepseek in desktop console',
                manual_required=['10句真实闭唇/唇齿音偏差','穿插与形变主观复核','真人相似度','首帧启动与流畅度人工计时'],
                peak_memory='Blender log peak; not operating system process peak',cost='no billable API calls in this suite')
    cache=PROJECT/'.cache/digitalhuman'
    command=json.loads((PROJECT/'renderer-command.json').read_text('utf-8-sig'))
    base=json.loads((PROJECT/'configs/head-draft.json').read_text('utf-8-sig'))
    base=apply_profile(base,'draft')
    last_speech=None
    def run(name,config):
        config=resolve(config)
        started=time.perf_counter()
        key=cache_key(config)
        existed=lookup(cache,config) is not None
        with key_lock(cache,key):
            media=lookup(cache,config)
            if media is None:
                media=generate(cache,config,command)
        first=time.perf_counter()-started
        started=time.perf_counter()
        assert lookup(cache,config)==media
        second=time.perf_counter()-started
        path=output/(name+'.json');path.write_text(json.dumps(config,ensure_ascii=False,indent=2),'utf-8')
        # Check the actual Blender timeline used to render, not only Python reference channels.
        manifests=[]
        for p in (PROJECT/'work/render-jobs').glob('*/config.json'):
            if json.loads(p.read_text('utf-8'))==config:
                manifests.append(p)
        job=max(manifests,key=lambda p:p.stat().st_mtime).parent
        timeline=json.loads((job/'frames/mouth-timeline.json').read_text('utf-8'))
        assert len(timeline)==config['performance']['frames']
        for point in timeline:
            assert all(math.isfinite(v) and 0<=v<=1 for v in point['weights'].values())
            assert sum(point['weights'].values()) <= 1.00001
            assert all(math.isfinite(v) for v in point['controls'].values())
        assert all(abs(v)<1e-7 for v in timeline[-1]['weights'].values())
        for name_key in ('smile','brow','surprise','gaze','pitch','turn','arm','breath','hair'):
            assert abs(timeline[0]['controls'][name_key])<1e-7
            assert abs(timeline[-1]['controls'][name_key])<1e-7
        stage_report=json.loads((job/'report.json').read_text('utf-8'))
        assert stage_report['success']
        peaks=re.findall(r'Peak ([0-9.]+)M', (job/'blender.log').read_text('utf-8',errors='replace'))
        record=dict(blender_reported_peak_mib=max(map(float,peaks)) if peaks else None, name=name,key=key,video=str(media),first_seconds=round(first,3),already_cached=existed,
                    second_lookup_seconds=round(second,6),stages=stage_report['stages'],
                    width=config['quality']['width'],height=config['quality']['height'],fps=config['quality']['fps'],
                    frames=config['performance']['frames'],technical_pass=True,visual_review='pending',job=str(job))
        report['cases'].append(record)
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print(f'ACCEPT {name}: {first:.2f}s; second cache {second:.4f}s',flush=True)
    try:
        first_path,first_bundle,_=prepare_speech(SENTENCES[0])
        first=copy.deepcopy(base)
        first['performance'].update(text=SENTENCES[0],tts_file=str(first_path),frames=math.ceil(first_bundle['duration_seconds']*24)+4)
        run('preview-combined',apply_profile(first,'preview'))
        for i,text in enumerate(SENTENCES):
            path,bundle,hits=prepare_speech(text)
            c=copy.deepcopy(base)
            c['scene']['camera']='fixed-half-body'
            c['performance'].update(text=text,tts_file=str(path),frames=math.ceil(bundle['duration_seconds']*24)+4,
                                    expression=('neutral-with-blink','smile','curious','surprised')[i%4],
                                    motion_revision=('idle-v1','nod','shake','explain')[i%4])
            run(f'speech-{i+1:02d}',c)
            if i==0:
                last_speech=c
                # A shared prepared scene is available directly in the desktop preset list.
                folder=PROJECT/'work/text';folder.mkdir(parents=True,exist_ok=True)
                (folder/'render-config.json').write_text(json.dumps(c,ensure_ascii=False,indent=2),'utf-8')
        for expression in ('neutral-with-blink','smile','curious','surprised'):
            c=copy.deepcopy(base);c['performance'].update(expression=expression,frames=48,motion_revision='still')
            c['scene']['camera']='head-closeup'
            run('expression-'+expression,c)
        for hair in ('none','static','sway'):
            c=copy.deepcopy(base);c['quality']['hair']=hair
            c['performance'].update(frames=48,motion_revision='explain',expression='smile')
            run('hair-'+hair,c)
        media,hit=prepare_reel(last_speech)
        (PROJECT/'work/desktop').mkdir(parents=True,exist_ok=True)
        (PROJECT/'work/desktop/reel.json').write_text(json.dumps(dict(media_path=str(media),hit=hit)),'utf-8')
        started=time.perf_counter();again,hit=prepare_reel(last_speech)
        assert hit and again==media
        report['reel']=dict(media=str(media),second_hit=hit,second_seconds=round(time.perf_counter()-started,3),transition='120ms black fade')
        # Check saved, baked Blender controls in one background process.
        with (output/'baked-scenes.log').open('w',encoding='utf-8') as log:
            subprocess.run([__import__('render_settings').tool_paths()['blender'],'--background','--factory-startup','--python-exit-code','1',
                            '--python',str(PROJECT/'tools/inspect_behavior.py'),'--',str(output/'report.json')],
                           check=True,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        report['baked_scene_checks']=json.loads((output/'baked-scene-checks.json').read_text('utf-8'))
        report['success']=True
    finally:
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('TECHNICAL ACCEPTANCE PASSED; subjective checks remain pending',flush=True)


if __name__=='__main__':
    with key_lock(PROJECT/'.cache/tasks', 'acceptance'):
        main()

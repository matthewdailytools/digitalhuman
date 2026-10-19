"""Render real five-control fixtures; keep plans, videos, saved scenes and cache evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from render_settings import PROJECT, tool_paths
from cache_pipeline import cache_key


def main():
    output = PROJECT/'work/micro-acceptance'
    output.mkdir(parents=True, exist_ok=True)
    report = {'success': False, 'cases': []}
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    for name in ('eye_close', 'gaze', 'smile', 'mouth_open', 'nod', 'mock-sequence'):
        folder = output/name
        folder.mkdir(exist_ok=True)
        if name == 'mock-sequence':
            request = dict(mode='ai',provider='mock',instruction='用5秒依次闭眼、看向画面左、微笑、张嘴，最后轻轻点头。')
        else:
            values = dict(eye_close=0,smile=0,mouth_open=0,nod=0)
            if name in values:
                values[name] = 1
            request = dict(mode='manual',controls=values,gaze=[-1,1] if name == 'gaze' else [0,0],duration=2)
        request['quality'] = dict(profile='draft',width=640,height=360,fps=24,samples=4,hair='static',camera='head-closeup')
        path = folder/'request.json'
        path.write_text(json.dumps(request,ensure_ascii=False),'utf-8')
        command = [sys.executable,str(PROJECT/'micro_pipeline.py'),'--request',str(path),'--output',str(folder)]
        started = time.perf_counter()
        with (folder/'task.log').open('w',encoding='utf-8') as log:
            subprocess.run(command,cwd=PROJECT,stdout=log,stderr=subprocess.STDOUT,check=True,env=env)
        first_seconds = time.perf_counter()-started
        answer = json.loads((folder/'answer.json').read_text('utf-8'))
        config = answer['config']
        # Match an actual validated renderer job by its fully resolved cache key.
        candidates = []
        for entry in (PROJECT/'work/render-jobs').iterdir():
            try:
                c = json.loads((entry/'config.json').read_text('utf-8'))
                r = json.loads((entry/'report.json').read_text('utf-8'))
                if r['success'] and cache_key(c) == cache_key(config):
                    candidates.append(entry)
            except (OSError,ValueError,KeyError):
                pass
        if not candidates:
            raise ValueError('No validated Blender scene found: '+name)
        job = max(candidates,key=lambda p:p.stat().st_mtime_ns)
        started = time.perf_counter()
        with (folder/'reuse.log').open('w',encoding='utf-8') as log:
            subprocess.run(command,cwd=PROJECT,stdout=log,stderr=subprocess.STDOUT,check=True,env=env)
        status = json.loads((folder/'result.json').read_text('utf-8'))
        assert status['video_hit'] and 'CACHE HIT' in (folder/'reuse.log').read_text('utf-8')
        report['cases'].append(dict(name=name,job=str(job),media_path=answer['media_path'],
                                    config=config,first_seconds=first_seconds,reuse_seconds=time.perf_counter()-started,
                                    video_hit_on_repeat=True,source=status['source']))
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print('CASE PASSED',name,flush=True)
    command = [tool_paths()['blender'],'--background','--factory-startup','--python-exit-code','1',
               '--python',str(PROJECT/'tools/inspect_micro_controls.py'),'--',str(output/'report.json')]
    with (output/'inspect.log').open('w',encoding='utf-8') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    report['success'] = True
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('FIVE CONTROLS ACCEPTED',flush=True)


if __name__=='__main__':main()

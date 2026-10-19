"""Scan rig -> actual rendered frames -> validated, silent H.264 video."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from render_settings import PROJECT,tool_paths,sha256
from scanned_settings import resolve
from renderer import probe,validate_video


def render(config_path,output):
    snapshot=json.loads(Path(config_path).read_text('utf-8-sig'));config=resolve(snapshot)
    if config!=snapshot:raise ValueError('写实资产或脚本已变化，请重新准备配置')
    tools=tool_paths();q=config['quality'];p=config['performance']
    job=PROJECT/'work/render-jobs'/uuid.uuid4().hex;job.mkdir(parents=True)
    (job/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),'utf-8')
    report=dict(success=False,job=str(job),stages={},has_audio=False)
    def stage(name,command,timeout):
        print(name+': '+str(job),flush=True);start=time.monotonic()
        with (job/(name+'.log')).open('w',encoding='utf-8') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=timeout,cwd=PROJECT,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        report['stages'][name]=time.monotonic()-start
    try:
        frames=job/'frames'
        stage('blender',[tools['blender'],'--background','--factory-startup','--disable-autoexec','--threads','4',
                        '--python-exit-code','1','--python',str(PROJECT/'tools/render_scanned_motion.py'),'--',
                        '--config',str(job/'config.json'),'--output',str(frames)],7200)
        for frame in range(1,p['frames']+1):
            if not (frames/f'frame_{frame:04d}.png').is_file():raise ValueError('写实视频缺少渲染帧')
        encoded=job/'video.mp4'
        stage('encode',[tools['ffmpeg'],'-v','error','-y','-framerate',str(q['fps']),'-start_number','1','-i',
                        str(frames/'frame_%04d.png'),'-an','-frames:v',str(p['frames']),'-c:v','libx264',
                        '-threads','2','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(encoded)],300)
        data=probe(tools['ffprobe'],encoded,True);validate_video(data,config,False)
        (job/'video-probe.json').write_text(json.dumps(data,indent=2),'utf-8')
        stage('decode',[tools['ffmpeg'],'-v','error','-xerror','-i',str(encoded),'-f','null','-'],300)
        if resolve(config)!=config:raise ValueError('渲染期间写实资产发生变化，未发布缓存')
        output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(encoded,output)
        report.update(success=True,output=str(output),video_sha256=sha256(output))
        print('RENDER VALIDATED: '+str(encoded),flush=True)
    finally:
        (job/'report.json').write_text(json.dumps(report,indent=2),'utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:render(args.config,args.output)
    except Exception as error:print('写实渲染失败：'+str(error),file=sys.stderr);sys.exit(1)

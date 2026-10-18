"""Versioned cached state reels with short fades and bounded playback response tokens."""
from pathlib import Path
import json
import subprocess
from cache_pipeline import lookup, cache_key, generate
from render_settings import PROJECT, resolve, tool_paths
from layer_cache import cached_layer, digest
from quality_profiles import apply_profile

STATES=('idle','listening','thinking','speaking')


class ResponseGate:
    def __init__(self):
        self.revision=0
        self.pending=None
    def begin(self):
        self.revision+=1
        self.pending=self.revision
        return self.revision
    def stop(self):
        self.revision+=1
        self.pending=None
    def accepts(self, token):
        return token==self.pending==self.revision


def state_config(state, profile='draft', speaking=None):
    if state not in STATES:
        raise ValueError('未知播放状态')
    if state=='speaking':
        if not speaking or not speaking.get('performance',{}).get('tts_file'):
            raise ValueError('speaking 需要已生成的讲话配置')
        config=apply_profile(speaking,profile)
        config['performance']['frames']=(speaking['performance']['frames']*config['quality']['fps']+speaking['quality']['fps']-1)//speaking['quality']['fps']
        # Use the same framing for the entire state reel.
        config['scene']['camera']='fixed-half-body'
        return resolve(config)
    config=json.loads((PROJECT/'configs/head-draft.json').read_text('utf-8-sig'))
    config=apply_profile(config,profile)
    config['scene']['camera']='fixed-half-body'
    config['performance'].update(frames=48,expression='neutral-with-blink' if state=='idle' else 'curious',
                                 motion_revision='idle-v1' if state=='idle' else 'still',
                                 gaze='left' if state=='thinking' else 'camera', strength=0.35)
    return resolve(config)


def prepare_reel(speaking, profile='draft', cache=None):
    cache=Path(cache or PROJECT/'.cache/digitalhuman')
    command=json.loads((PROJECT/'renderer-command.json').read_text('utf-8-sig'))
    media=[]
    from layer_cache import key_lock
    for state in STATES:
        config=state_config(state,profile,speaking)
        with key_lock(cache,cache_key(config)):
            path=lookup(cache,config)
            if path is None:
                path=generate(cache,config,command)
        print(f'STATE {state}: {path}',flush=True)
        media.append(path)
    identity=dict(kind='state-reel-v1', clips=[digest(p) for p in media], transition='black-fade-120ms',profile=profile)
    def produce(folder):
        chunks=[]
        for i,path in enumerate(media):
            config=state_config(STATES[i],profile,speaking)
            duration=config['performance']['frames']/config['quality']['fps']
            target=folder/f'part-{i}.mp4'
            cmd=[tool_paths()['ffmpeg'],'-v','error','-y','-i',str(path)]
            if i<3:
                cmd+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
            cmd+=['-map','0:v:0','-map','0:a:0' if i==3 else '1:a:0','-vf',f'fade=t=in:st=0:d=0.12,fade=t=out:st={max(0,duration-0.12)}:d=0.12',
                  '-af',f'aresample=48000,aformat=channel_layouts=stereo,afade=t=in:d=0.12,afade=t=out:st={max(0,duration-0.12)}:d=0.12',
                  '-t',str(duration),'-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(target)]
            subprocess.run(cmd,check=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            chunks.append(target)
        # File names generated internally; no arbitrary input can inject concat directives.
        playlist=folder/'list.txt'
        playlist.write_text('\n'.join(f"file '{p.name}'" for p in chunks),'utf-8')
        subprocess.run([tool_paths()['ffmpeg'],'-v','error','-y','-f','concat','-safe','1','-i',str(playlist),
                        '-c','copy','-movflags','+faststart',str(folder/'reel.mp4')],check=True,timeout=180,
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        subprocess.run([tool_paths()['ffmpeg'],'-v','error','-xerror','-i',str(folder/'reel.mp4'),'-f','null','-'],
                       check=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for p in chunks:
            p.unlink()
        playlist.unlink()
        (folder/'states.json').write_text(json.dumps({'states':STATES,'transition':'120ms black fade, not seamless','source_keys':[p.parent.name for p in media]}),'utf-8')
    folder,hit=cached_layer(PROJECT/'.cache/layers/reels',identity,produce)
    return folder/'reel.mp4',hit


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--profile',default='draft');args=parser.parse_args()
    media,hit=prepare_reel(json.loads(Path(args.config).read_text('utf-8-sig')),args.profile)
    Path(args.output).write_text(json.dumps({'media_path':str(media),'hit':hit}), 'utf-8')
    print(f'REEL CACHE HIT: {hit}',flush=True)

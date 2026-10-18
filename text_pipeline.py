"""Text -> separately cached SAPI audio -> approximate face events -> renderer config.
SAPI is a local test fallback, not an external TTS nor phoneme alignment.
"""
import argparse
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
import wave
from layer_cache import cached_layer, digest
from quality_profiles import apply_profile
from speech import load_bundle
from render_settings import PROJECT, sha256
from ai_adapter import chat

ROOT = PROJECT/'.cache/layers'


def prepare_speech(text, root=ROOT, voice_revision='windows-huihui-v1'):
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 120:
        raise ValueError('测试台词需为1—120字，音频不得超过30秒')
    identity = dict(text=text, provider='windows-sapi-test', voice=voice_revision, rate=0, format='pcm22050-mono16',
                    adapter=sha256(PROJECT/'tools/mock_tts_voice.ps1'))
    def audio_producer(folder):
        request = folder/'request.json'
        request.write_text(json.dumps({'segments':[{'text': text}]}, ensure_ascii=False), 'utf-8')
        command = ['powershell', '-NoProfile', '-File', str(PROJECT/'tools/mock_tts_voice.ps1'),
                   '-Request', str(request), '-Output', str(folder)]
        subprocess.run(command, check=True, capture_output=True, timeout=120,
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (folder/'syllable_00.wav').rename(folder/'audio.wav')
        with wave.open(str(folder/'audio.wav'),'rb') as stream:
            duration = stream.getnframes()/stream.getframerate()
        if not 0 < duration <= 29.5:
            raise ValueError('语音超过29.5秒，请缩短台词')
    audio_dir, audio_hit = cached_layer(Path(root)/'audio', identity, audio_producer)
    audio = audio_dir/'audio.wav'
    face_id = dict(audio_sha256=digest(audio), mapping='amplitude-cycled-vowels-test-v1', text=text,
                   adapter=sha256(Path(__file__)))
    def face_producer(folder):
        with wave.open(str(audio),'rb') as stream:
            rate = stream.getframerate()
            samples = array('h', stream.readframes(stream.getnframes()))
        duration = len(samples)/rate
        events=[]
        step=round(rate*0.12)
        for i, start in enumerate(range(0,len(samples),step)):
            values=samples[start:start+step]
            rms=(sum(v*v for v in values)/len(values))**0.5
            if rms > 180:
                events.append(dict(start=start/rate,end=min(len(samples),start+step)/rate,
                                   viseme=('A','E','I','O','U')[i%5],strength=min(1,rms/1800)))
        if not events:
            raise ValueError('合成声音静音')
        bundle=dict(schema_version=1,source='sapi-amplitude-test', alignment='amplitude-only-not-phoneme-alignment',
                    text=text,audio_file=str(audio.resolve()),audio_sha256=digest(audio),duration_seconds=duration,
                    events=events)
        (folder/'tts.json').write_text(json.dumps(bundle,ensure_ascii=False),'utf-8')
        load_bundle(folder/'tts.json')
    face_dir, face_hit = cached_layer(Path(root)/'face',face_id,face_producer)
    bundle=load_bundle(face_dir/'tts.json')
    return face_dir/'tts.json',bundle,dict(audio_hit=audio_hit,face_hit=face_hit)


def prepare(request, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    text=request['text']
    expression=request.get('expression','neutral-with-blink')
    motion=request.get('motion','idle-v1')
    status={'chat_hit':None, 'provider':request.get('provider','mock'), 'tts':'local-windows-sapi-test',
            'alignment':'amplitude-only-not-phoneme-alignment', 'cost':None}
    if request.get('dialogue'):
        reply, hit=chat(text,ROOT/'chat',request.get('provider','mock'),request.get('model'),request.get('context',[]))
        text,expression,motion=reply['text'],reply['expression'],reply['motion']
        status.update(chat_hit=hit, usage=reply.get('usage'), returned_model=reply.get('returned_model'))
    path,bundle,hits=prepare_speech(text)
    status.update(hits)
    status['text']=text
    status['context']=request.get('context', []) + ([{'role':'user','content':request['text']},{'role':'assistant','content':text}] if request.get('dialogue') else [])
    config=json.loads((PROJECT/'configs/head-draft.json').read_text('utf-8-sig'))
    config=apply_profile(config,request.get('profile','draft'))
    config['scene']['camera']=request.get('camera','head-closeup')
    config['performance'].update(text=text,expression=expression,motion_revision=motion,
                                tts_file=str(path.resolve()),frames=math.ceil(bundle['duration_seconds']*config['quality']['fps'])+4)
    from render_settings import resolve
    config=resolve(config)
    (output/'render-config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),'utf-8')
    (output/'result.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(status,ensure_ascii=False),flush=True)
    return config


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:
        prepare(json.loads(Path(args.request).read_text('utf-8-sig')), args.output)
    except Exception as error:
        print(f'语音/对话准备失败: {error}',file=sys.stderr)
        raise SystemExit(1)

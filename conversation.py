"""One response task: dialogue -> voice/face layer -> video cache. No player side effects."""
import argparse
import json
from pathlib import Path
from text_pipeline import prepare
from render_settings import PROJECT
from cache_pipeline import generate,lookup,cache_key
from layer_cache import key_lock


def run(request,output):
    output=Path(output)
    config=prepare(request,output)
    cache=PROJECT/'.cache/digitalhuman'
    with key_lock(cache,cache_key(config)):
        media=lookup(cache,config)
        if media is None:
            command=json.loads((PROJECT/'renderer-command.json').read_text('utf-8-sig'))
            media=generate(cache,config,command)
        else:
            print('CACHE HIT: generation skipped',flush=True)
    (output/'answer.json').write_text(json.dumps({'media_path':str(media),'config':config},ensure_ascii=False),'utf-8')
    return media


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:run(json.loads(Path(args.request).read_text('utf-8-sig')),args.output)
    except Exception as error:
        print(f'回答任务失败: {error}')
        raise SystemExit(1)

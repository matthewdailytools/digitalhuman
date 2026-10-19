"""Manual/AI five-control request -> reviewed timeline -> cached Blender video, no TTS."""
import argparse
import json
import math
from pathlib import Path
from ai_motion import plan_actions
from micro_control import manual_plan, validate_plan, describe
from render_settings import PROJECT, resolve, validate
from quality_profiles import apply_profile
from cache_pipeline import cache_key, lookup, generate
from layer_cache import key_lock


def prepare(request, output):
    allowed = {'mode', 'controls', 'gaze', 'duration', 'instruction', 'provider', 'model', 'quality', 'character'}
    if not isinstance(request, dict) or set(request)-allowed or request.get('mode') not in ('manual', 'ai'):
        raise ValueError('无效的五项控制请求')
    # Reject unsupported render settings before any potentially billable AI request.
    quality = request.get('quality', {})
    if not isinstance(quality, dict) or set(quality)-{'profile', 'width', 'height', 'fps', 'samples', 'hair', 'camera'}:
        raise ValueError('无效的五项控制画质参数')
    character=request.get('character','procedural-head')
    if character not in ('procedural-head','scanned-head'):raise ValueError('未知五项控制角色')
    if character=='scanned-head':
        from scanned_settings import base_config,resolve as resolve_scan
        config=base_config(quality)
        resolver=resolve_scan
    else:
        config = json.loads((PROJECT/'configs/head-draft.json').read_text('utf-8-sig'))
        config = apply_profile(config, quality.get('profile', 'draft'))
        config['quality'].update({k: v for k, v in quality.items() if k not in ('profile', 'camera')})
        config['scene']['camera'] = quality.get('camera', 'head-closeup')
        config['performance'].update(frames=2, text='', expression='neutral-with-blink', motion_revision='still')
        validate(config)
        resolver=resolve
    status = {'mode': request['mode'], 'plan_hit': None}
    if request['mode'] == 'manual':
        plan = manual_plan(request.get('controls'), request.get('gaze'), request.get('duration'))
        status['source'] = 'manual-controls'
    else:
        if character=='scanned-head':config=resolver(config)
        result, hit = plan_actions(request.get('instruction'), PROJECT/'.cache/layers/motion-plans',
                                   request.get('provider', 'mock'), request.get('model'))
        plan = result['plan']
        status.update({k: v for k, v in result.items() if k != 'plan'})
        status.update(plan_hit=hit, instruction=request['instruction'])
    status['plan'] = validate_plan(plan)
    fps = config['quality']['fps']
    if type(fps) is not int or not 1 <= fps <= 60:
        raise ValueError('无效帧率')
    config['performance'] = dict(text='', expression='neutral-with-blink', motion_revision='still',
                                 frames=math.ceil(plan['duration']*fps)+1, micro_control=plan)
    config = resolver(config)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output/'render-config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), 'utf-8')
    (output/'result.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), 'utf-8')
    (output/'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), 'utf-8')
    print(f"五项控制来源：{status['source']}；计划缓存命中：{status['plan_hit']}", flush=True)
    print(describe(plan), flush=True)
    return config, status


def run(request, output):
    config, status = prepare(request, output)
    cache = PROJECT/'.cache/digitalhuman'
    with key_lock(cache, cache_key(config)):
        media = lookup(cache, config)
        hit = media is not None
        if not hit:
            command = (["{python}","{project}/scanned_renderer.py","--config","{config}","--output","{output}"]
                       if config['character']['id']=='scanned-head' else
                       json.loads((PROJECT/'renderer-command.json').read_text('utf-8-sig')))
            media = generate(cache, config, command)
        else:
            print('CACHE HIT: generation skipped', flush=True)
    status['video_hit'] = hit
    (Path(output)/'result.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), 'utf-8')
    (Path(output)/'answer.json').write_text(json.dumps({'media_path': str(media), 'config': config}, ensure_ascii=False), 'utf-8')
    return media


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        run(json.loads(Path(args.request).read_text('utf-8-sig')), args.output)
    except Exception as error:
        print('五项控制任务失败：'+str(error), flush=True)
        raise SystemExit(1)

"""Strict five-control timelines, shared by desktop, AI and Blender. Seconds, not frames."""
import copy
import math
from speech import number

CONTROLS = ('eye_close', 'gaze', 'smile', 'mouth_open', 'nod')
MAX_DURATION = 15


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {'schema_version', 'duration', 'auto_blink', 'events'}:
        raise ValueError('动作计划仅支持 schema_version、duration、auto_blink、events')
    if type(plan['schema_version']) is not int or plan['schema_version'] != 1:
        raise ValueError('动作计划版本无效')
    duration = plan['duration']
    if not number(duration) or not 1 <= duration <= MAX_DURATION or type(plan['auto_blink']) is not bool:
        raise ValueError('动作时长须为1—15秒，auto_blink须为布尔值')
    events = plan['events']
    if not isinstance(events, list) or not 1 <= len(events) <= 40:
        raise ValueError('动作计划需要1—40个事件')
    previous = {}
    for event in events:
        if not isinstance(event, dict) or set(event) != {'control', 'start', 'end', 'value'}:
            raise ValueError('每个动作仅支持 control、start、end、value')
        control, start, end, value = (event[k] for k in ('control', 'start', 'end', 'value'))
        if not isinstance(control, str) or control not in CONTROLS:
            raise ValueError('只允许闭眼、注视、微笑、张嘴、点头五项控制')
        if not all(number(x) for x in (start, end)) or not 0 <= start < end <= duration or end-start < 0.2:
            raise ValueError('动作事件需在时间轴内，持续至少0.2秒')
        if start < previous.get(control, 0):
            raise ValueError('同一控制的事件必须按时间排列，且不能重叠')
        previous[control] = end
        if control == 'gaze':
            if not isinstance(value, list) or len(value) != 2 or not all(number(x) and -1 <= x <= 1 for x in value):
                raise ValueError('注视值须为[x,y]，各分量在-1—1之间；正数为画面右/上')
        elif not number(value) or not 0 <= value <= 1:
            raise ValueError('控制强度须为0—1的有限数字')
    return plan


def manual_plan(values, gaze, duration):
    if not isinstance(values, dict) or set(values) != set(CONTROLS)-{'gaze'}:
        raise ValueError('请分别设置闭眼、微笑、张嘴和点头强度')
    events = [dict(control=name, start=0, end=duration, value=copy.deepcopy(gaze if name == 'gaze' else values[name]))
              for name in CONTROLS]
    return validate_plan(dict(schema_version=1, duration=duration, auto_blink=False, events=events))


def sample_plan(plan, time_seconds):
    """Caller validates once. Smooth finite pulses return to neutral at both endpoints."""
    result = dict(eye_close=0.0, gaze_x=0.0, gaze_y=0.0, smile=0.0, mouth_open=0.0, pitch=0.0)
    if not 0 < time_seconds < plan['duration']:
        return result
    if plan['auto_blink']:
        result['eye_close'] = max(0, 1-abs((time_seconds % 2.4)-1.0)/0.12)
    for event in plan['events']:
        start, end = event['start'], event['end']
        if not start < time_seconds < end:
            continue
        u = (time_seconds-start)/(end-start)
        ramp = min(0.25, (end-start)/4)
        x = min(1, (time_seconds-start)/ramp, (end-time_seconds)/ramp)
        weight = x*x*(3-2*x)
        name, value = event['control'], event['value']
        if name == 'gaze':
            result['gaze_x'], result['gaze_y'] = value[0]*weight, value[1]*weight
        elif name == 'nod':
            result['pitch'] = math.radians(12)*value*math.sin(math.pi*u)**2
        elif name == 'eye_close':
            result[name] = max(result[name], value*weight)
        else:
            result[name] = value*weight
    return result


def describe(plan):
    validate_plan(plan)
    names = dict(eye_close='闭眼', gaze='注视', smile='微笑', mouth_open='张嘴', nod='点头')
    lines = [f"时长 {plan['duration']:g} 秒；自动眨眼：{'开' if plan['auto_blink'] else '关'}"]
    for e in plan['events']:
        lines.append(f"{e['start']:g}—{e['end']:g} 秒：{names[e['control']]} {e['value']}")
    return '\n'.join(lines)

"""Deterministic bounded behavior channels, independent of Blender and AI."""
import math

EXPRESSIONS = ('neutral-with-blink', 'smile', 'curious', 'surprised')
MOTIONS = ('idle-v1', 'still', 'nod', 'shake', 'explain')
GAZES = ('camera', 'left', 'right')


def envelope(t, duration, enter=0.25, leave=0.25):
    x = max(0.0, min(1.0, t / max(enter, 0.001), (duration-t) / max(leave, 0.001)))
    return x*x*(3-2*x)


def channels(t, duration, expression='neutral-with-blink', strength=0.6, motion='idle-v1', gaze='camera', enter=0.25, leave=0.25):
    if expression not in EXPRESSIONS or motion not in MOTIONS or gaze not in GAZES:
        raise ValueError('Unsupported behavior')
    e = envelope(t, duration, enter, leave)
    amount = max(0, min(1, strength))*e
    phase = t / max(duration, 0.001) * math.tau
    result = dict(smile=amount if expression == 'smile' else 0,
                  brow=amount if expression in ('curious', 'surprised') else 0,
                  surprise=amount if expression == 'surprised' else 0,
                  gaze=(-1 if gaze == 'left' else 1 if gaze == 'right' else 0)*0.009*e,
                  pitch=0.0, turn=0.0, arm=0.0, breath=0.003*(1-math.cos(phase)),
                  hair=math.radians(2)*math.sin(phase*2)*e)
    if motion == 'idle-v1':
        result.update(pitch=math.radians(1.2)*math.sin(phase*2), turn=math.radians(7)*math.sin(phase))
    elif motion == 'nod':
        result['pitch'] = math.radians(8)*math.sin(phase*2)*e
    elif motion == 'shake':
        result['turn'] = math.radians(12)*math.sin(phase*2)*e
    elif motion == 'explain':
        result['arm'] = math.radians(28)*e*(0.7+0.3*math.sin(phase))
    if motion == 'still':
        result['breath'] = 0
    # Periodic blink independent of emotion/head channels; endpoints open.
    result['blink'] = max(0, 1-abs((t % 2.4)-1.0)/0.12)*e
    return result

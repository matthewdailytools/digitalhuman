"""Quality presets expand to concrete supported parameters before cache hashing."""
import copy

PROFILES = {
    'draft': dict(profile='draft', width=640, height=360, fps=24, samples=4, hair='static', skin='simple', body='bust'),
    'preview': dict(profile='preview', width=960, height=540, fps=24, samples=16, hair='sway', skin='procedural', body='bust'),
}


def apply_profile(config, name):
    if name == 'final':
        raise ValueError('final 需要远端 GPU 与高质量人物后端，尚未接入')
    if name not in PROFILES:
        raise ValueError('未知质量档位')
    result = copy.deepcopy(config)
    result['quality'] = copy.deepcopy(PROFILES[name])
    return result

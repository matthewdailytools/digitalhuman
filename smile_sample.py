"""Deterministic desktop demonstration; no AI call or new low-level AI controls."""
def smile_plan():
    from micro_control import validate_plan
    return validate_plan(dict(schema_version=1,duration=6,auto_blink=False,events=[
        dict(control='smile',start=.25,end=1.65,value=.35),
        dict(control='smile',start=1.85,end=3.25,value=.9),
        dict(control='smile',start=3.45,end=5.8,value=.9),
        dict(control='mouth_open',start=3.7,end=5.6,value=.65),
        dict(control='eye_close',start=4.8,end=5.5,value=1),
    ]))

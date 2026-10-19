"""Exercise the actual persistent native viewport and request GPU viewport snapshots."""
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from realtime_preview import RealtimePreview,CHANNELS

OUTPUT=ROOT/'work/realtime-acceptance';OUTPUT.mkdir(parents=True,exist_ok=True)

def main():
    live=RealtimePreview();before=set((ROOT/'work/render-jobs').iterdir());checks=[];pid=None
    def wait(predicate,timeout=60):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            state=live.snapshot()
            if state['phase'] in ('failed','stopped'):raise RuntimeError(str(state))
            if predicate(state):return state
            time.sleep(.08)
        raise TimeoutError(str(live.snapshot()))
    def send(values,mode='solid',hair=False,capture=False):
        controls=dict.fromkeys(CHANNELS,0.0);controls.update(values)
        seq=live.publish(controls,mode=mode,hair=hair,capture=capture)
        state=wait(lambda s:s.get('seq')==seq and max(abs(s['controls'][k]-v) for k,v in controls.items())<.001,120)
        assert state['pid']==pid,'Blender restarted for a control change'
        expected=dict(EyeClose=controls['eye_close'],SmileCorners=controls['smile'],SmileCheeks=controls['smile'],
                      SmileLids=controls['smile']*(1-controls['eye_close']),SmileOpenCorrective=controls['smile']*controls['mouth_open'])
        for name,value in expected.items():assert abs(state['shape_values'][name]-value)<.003,(name,state)
        assert abs(state['jaw_angle']-.26*controls['mouth_open'])<.001
        assert abs(state['head_angle']-math.radians(10.8)*controls['nod'])<.001
        assert abs(state['eye_angles'][2]-.24*controls['gaze_x'])<.001
        assert abs(state['eye_angles'][0]+.16*controls['gaze_y'])<.001
        if capture:
            image=Path(state['session'])/f'viewport-{seq}.png'
            wait(lambda s:image.is_file(),120)
            from PIL import Image,ImageStat
            with Image.open(image) as source:
                assert source.width>200 and source.height>200
                assert max(ImageStat.Stat(source.convert('RGB')).stddev)>5
                center=source.convert('RGB').crop((source.width*.35,source.height*.3,source.width*.65,source.height*.65))
                assert max(ImageStat.Stat(center).stddev)>5,'Face region is blank or black'
            state['capture']=str(image)
        checks.append(state);print('REALTIME ACCEPTED',mode,controls,flush=True)
        return state
    def lock_file(path):
        # Filesystem fault injection, not desktop input automation. Windows share=0
        # reproduces the exact PermissionError seen in the user's heartbeat log.
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,
                                    wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
        end=time.monotonic()+2
        while True:
            handle=kernel.CreateFileW(str(path),0x80000000,0,None,3,0x80,None)
            if handle!=ctypes.c_void_p(-1).value:return kernel,handle
            if time.monotonic()>end:raise ctypes.WinError(ctypes.get_last_error())
            time.sleep(.01)
    try:
        live.start();first=wait(lambda s:s['phase']=='running',120);pid=first['pid']
        assert first['hair_visible'] and first['hair_strands']==42000,'Original short hair should be visible by default'
        print('REALTIME READY',first,flush=True)
        lock_checks=[]
        for name in ('heartbeat.json','status.json'):
            kernel,handle=lock_file(live.session/name)
            try:
                seq=live.publish(dict(dict.fromkeys(CHANNELS,0),smile=.6))
                until=time.monotonic()+1.5
                while time.monotonic()<until:
                    state=live.snapshot()
                    assert state['phase']=='running' and state['pid']==pid,state
                    time.sleep(.05)
            finally:kernel.CloseHandle(handle)
            state=wait(lambda s:s.get('seq')==seq and abs(s['controls']['smile']-.6)<.001)
            assert not (live.session/'error.log').exists()
            lock_checks.append(dict(file=name,exclusive_lock_seconds=1.5,recovered=True,pid=pid))
            print('REALTIME LOCK RECOVERY',name,flush=True)
        send({})
        send(dict(smile=.85,mouth_open=.6),capture=True)
        send(dict(eye_close=1,smile=1,nod=.5,gaze_x=-.8,gaze_y=.4),capture=True)
        send({})
        # Keep movement active while measuring actual viewport draws, not timer ticks.
        started=time.monotonic()
        while time.monotonic()-started<8:
            t=time.monotonic()-started
            live.publish(dict(eye_close=0,gaze_x=.7*math.sin(t),gaze_y=0,
                              smile=.5+.4*math.sin(2*t),mouth_open=.3,nod=.2))
            live.snapshot();time.sleep(.1)
        moving=live.snapshot();print('REALTIME MOVING FPS',moving.get('viewport_draw_fps'),flush=True)
        live.publish(dict.fromkeys(CHANNELS,0),sample=True)
        started=time.monotonic();peaks=dict(smile=0,mouth_open=0,eye_close=0)
        while time.monotonic()-started<8:
            state=live.snapshot()
            for key in peaks:peaks[key]=max(peaks[key],state.get('controls',{}).get(key,0))
            time.sleep(.1)
        assert peaks['smile']>.85 and peaks['mouth_open']>.6 and peaks['eye_close']>.95,peaks
        assert not state['sample_playing'] and max(abs(v) for v in state['controls'].values())<.005
        send(dict(smile=.85),mode='eevee',capture=True)
        send(dict(smile=.85,mouth_open=.5),mode='eevee',hair=True,capture=True)
        send({},mode='solid')
        assert set((ROOT/'work/render-jobs').iterdir())==before,'Realtime unexpectedly started offline render jobs'
        report=dict(success=True,persistent_pid=pid,session=str(live.session),checks=checks,
                    solid_moving_draw_fps=moving.get('viewport_draw_fps'),gpu=moving.get('gpu'),
                    realtime_smile_sample_peaks=peaks,
                    exclusive_file_lock_recovery=lock_checks,
                    no_offline_render_jobs=True,measurement='Draw callback rate; not GPU profiling or phone performance')
        (OUTPUT/'report.json').write_text(json.dumps(report,indent=2),'utf-8')
    finally:
        live.stop();end=time.monotonic()+10
        while time.monotonic()<end and live.snapshot()['phase']=='stopping':time.sleep(.1)
    assert not live.process or live.process.poll() is not None
    print('REALTIME ACCEPTANCE COMPLETE',flush=True)

if __name__=='__main__':main()

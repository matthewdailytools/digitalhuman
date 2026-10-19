"""Own one persistent Blender viewport; exchange latest state through local atomic files."""
import json
import math
from pathlib import Path
import subprocess
import threading
import time
import uuid

from render_settings import PROJECT,tool_paths

CHANNELS=('eye_close','gaze_x','gaze_y','smile','mouth_open','nod')
MODES=('solid','eevee')


def validate_state(state):
    if not isinstance(state,dict) or set(state)!=set(CHANNELS):raise ValueError('实时控制字段不完整')
    for name,value in state.items():
        lo=-1 if name.startswith('gaze') else 0
        if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=1:
            raise ValueError('实时控制强度无效：'+name)
    return {k:float(state[k]) for k in CHANNELS}


def atomic_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(value,ensure_ascii=False),'utf-8')
        # Windows may briefly deny replacement while the other process reads.
        for attempt in range(8):
            try:temporary.replace(path);break
            except PermissionError:
                if attempt==7:raise
                time.sleep(.003)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path):
    """A missed IPC read is retried next tick, not a fatal Blender error."""
    try:return json.loads(Path(path).read_text('utf-8'))
    except (FileNotFoundError,PermissionError,json.JSONDecodeError):return None


def try_atomic_json(path,value):
    try:atomic_json(path,value);return True
    except PermissionError:return False


class HeartbeatWatch:
    """Monotonic lease; re-reading an unchanged stale file never renews it."""
    def __init__(self,now,timeout=45):
        self.last_seen=now;self.last_stamp=None;self.timeout=timeout

    def alive(self,message,now):
        stamp=message.get('time') if isinstance(message,dict) else None
        if type(stamp) in (int,float) and math.isfinite(stamp) and stamp!=self.last_stamp:
            self.last_stamp=stamp;self.last_seen=now
        return now-self.last_seen<=self.timeout


class RealtimePreview:
    def __init__(self,root=None):
        self.root=Path(root or PROJECT/'work/realtime');self.lock=threading.RLock()
        self.process=None;self.session=None;self.cancel=None;self.phase='stopped';self.error=''
        self.seq=0;self.last_heartbeat=0

    def start(self):
        with self.lock:
            if self.phase in ('loading','running','stopping'):return
            if self.process and self.process.poll() is None:raise ValueError('请先关闭已有实时窗口，再重新启动')
            self.session=self.root/uuid.uuid4().hex;self.session.mkdir(parents=True,exist_ok=True)
            self.cancel=threading.Event();self.phase='loading';self.error='';self.seq=0;self.process=None
            session,cancel=self.session,self.cancel
            self.publish(dict.fromkeys(CHANNELS,0))
        threading.Thread(target=self._launch,args=(session,cancel),daemon=True).start()

    def _launch(self,session,cancel):
        try:
            from scanned_assets import ensure_rig
            asset=ensure_rig()
            if cancel.is_set():return
            atomic_json(session/'session.json',dict(schema_version=1,rig_file=asset['rig_file'],rig_sha256=asset['rig_sha256']))
            atomic_json(session/'heartbeat.json',dict(time=time.time()))
            command=[tool_paths()['blender'],'--factory-startup','--disable-autoexec','--threads','4',
                     '--window-geometry','60','60','850','680','--python-exit-code','1',
                     '--python',str(PROJECT/'tools/realtime_viewport.py'),'--','--session',str(session)]
            with self.lock:
                if cancel.is_set():return
                with (session/'blender.log').open('w',encoding='utf-8') as log:
                    self.process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=PROJECT,
                                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except Exception as error:
            with self.lock:
                if self.session==session and not cancel.is_set():self.phase='failed';self.error=str(error)
        finally:
            with self.lock:
                if cancel.is_set() and self.session==session and self.process is None:self.phase='stopped'

    def publish(self,state,mode='solid',hair=False,sample=False,capture=False):
        state=validate_state(state)
        if mode not in MODES or any(type(x) is not bool for x in (hair,sample,capture)):
            raise ValueError('无效实时预览选项')
        with self.lock:
            if self.phase not in ('loading','running'):return None
            self.seq+=1
            atomic_json(self.session/'command.json',dict(schema_version=1,seq=self.seq,sent_at=time.time(),
                        controls=state,mode=mode,hair=hair,sample=sample,capture=capture))
            return self.seq

    def snapshot(self):
        with self.lock:
            if self.process and self.process.poll() is not None and self.phase in ('loading','running','stopping'):
                if self.phase!='stopping':self.error='Blender 窗口已关闭或退出，请查看会话日志'
                self.phase='stopped'
            if self.session and self.phase in ('loading','running'):
                if time.monotonic()-self.last_heartbeat>2:
                    if try_atomic_json(self.session/'heartbeat.json',dict(time=time.time())):self.last_heartbeat=time.monotonic()
                state=read_json(self.session/'status.json') or {}
                if state.get('phase')=='failed':self.phase='failed';self.error=state.get('error','实时窗口失败')
                elif state.get('phase')=='ready':self.phase='running'
            else:state={}
            return dict(state,phase=self.phase,error=self.error,session=str(self.session) if self.session else None,
                        pid=self.process.pid if self.process else None)

    def stop(self):
        with self.lock:
            if not self.cancel:return
            self.cancel.set();session=self.session;process=self.process
            self.phase='stopping' if process and process.poll() is None else 'stopped'
            atomic_json(session/'stop.json',dict(stop=True))
        if process and process.poll() is None:
            threading.Thread(target=self._finish,args=(session,process),daemon=True).start()

    def _finish(self,session,process):
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        with self.lock:
            if self.session==session:self.phase='stopped'

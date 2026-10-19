import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch

from desktop_console import Console
from realtime_preview import CHANNELS,RealtimePreview,atomic_json,validate_state,read_json,try_atomic_json,HeartbeatWatch


class RealtimeTests(unittest.TestCase):
    def test_heartbeat_lock_keeps_lease_but_unchanged_file_expires(self):
        watch=HeartbeatWatch(0)
        self.assertTrue(watch.alive({'time':100},1))
        self.assertTrue(watch.alive(None,20))
        self.assertTrue(watch.alive({'time':101},30))
        self.assertTrue(watch.alive({'time':101},74))
        self.assertFalse(watch.alive({'time':101},76))
        self.assertFalse(watch.alive({'time':float('nan')},77))

    def test_transient_read_and_status_write_failures_are_nonfatal(self):
        for error in (PermissionError(),FileNotFoundError(),json.JSONDecodeError('locked','',0)):
            with patch.object(Path,'read_text',side_effect=error):self.assertIsNone(read_json('heartbeat.json'))
        with patch('realtime_preview.atomic_json',side_effect=PermissionError()):
            self.assertFalse(try_atomic_json('status.json',{'phase':'ready'}))
        with patch('realtime_preview.atomic_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):try_atomic_json('status.json',{})

    def test_console_survives_heartbeat_write_contention(self):
        with tempfile.TemporaryDirectory() as folder:
            live=RealtimePreview(folder);live.session=Path(folder);live.phase='running'
            atomic_json(live.session/'status.json',{'phase':'ready','seq':7})
            with patch('realtime_preview.try_atomic_json',return_value=False):
                self.assertEqual(live.snapshot()['seq'],7)
                self.assertEqual(live.phase,'running');self.assertEqual(live.last_heartbeat,0)

    def test_invalid_controls_never_enter_ipc(self):
        base=dict.fromkeys(CHANNELS,0)
        for name,value in (('smile',float('nan')),('eye_close',True),('nod',-1),('gaze_x',1.1)):
            with self.subTest(name=name),self.assertRaises(ValueError):validate_state(dict(base,**{name:value}))
        with self.assertRaises(ValueError):validate_state(dict(base,command='execute'))
        self.assertEqual(validate_state(dict(base,gaze_x=-1))['gaze_x'],-1)

    def test_windows_reader_lock_retries_without_partial_json(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'state.json';original=Path.replace;attempts=[]
            def locked(path,destination):
                attempts.append(1)
                if len(attempts)<3:raise PermissionError('reader briefly holds target')
                return original(path,destination)
            with patch.object(Path,'replace',locked):atomic_json(target,{'seq':8})
            self.assertEqual(json.loads(target.read_text()),{'seq':8})
            self.assertEqual(len(list(Path(folder).iterdir())),1)

    def test_stop_while_loading_does_not_launch_orphan_blender(self):
        entered=threading.Event();release=threading.Event()
        def build():entered.set();release.wait(2);return {'rig_file':'unused','rig_sha256':'unused'}
        with tempfile.TemporaryDirectory() as folder,patch('scanned_assets.ensure_rig',side_effect=build),patch('realtime_preview.subprocess.Popen') as popen:
            live=RealtimePreview(folder);live.start();self.assertTrue(entered.wait(1))
            live.stop();release.set();end=time.monotonic()+2
            while time.monotonic()<end and live.phase!='stopped':time.sleep(.01)
            self.assertEqual(live.phase,'stopped');popen.assert_not_called()

    def test_start_is_idempotent_and_latest_state_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            live=RealtimePreview(folder)
            with patch.object(live,'_launch') as launch:
                live.start();first=live.session;live.start()
                end=time.monotonic()+1
                while not launch.called and time.monotonic()<end:time.sleep(.01)
            self.assertEqual(live.session,first);self.assertEqual(launch.call_count,1)
            live.publish(dict.fromkeys(CHANNELS,0))
            seq=live.publish(dict(dict.fromkeys(CHANNELS,0),smile=.8),mode='eevee',hair=True)
            message=json.loads((first/'command.json').read_text('utf-8'))
            self.assertEqual(message['seq'],seq);self.assertEqual(message['controls']['smile'],.8)
            self.assertTrue(message['hair']);live.stop()

    def test_native_slider_dispatch_and_mode_options(self):
        console=Console.__new__(Console);console.root=Mock();console.live_pending='pending';console.live=Mock();console.live.publish.return_value=2
        console.live_values={name:Mock() for name in CHANNELS}
        for value in console.live_values.values():value.get.return_value=.3
        console.live_mode=Mock();console.live_mode.get.return_value='实时材质'
        console.live_hair=Mock();console.live_hair.get.return_value=True;console.live_status=Mock()
        Console.live_send(console,sample=True)
        self.assertIsNone(console.live_pending)
        console.root.after_cancel.assert_called_once_with('pending')
        self.assertEqual(console.live.publish.call_args.kwargs,dict(mode='eevee',hair=True,sample=True))
        self.assertEqual(console.live.publish.call_args.args[0]['smile'],.3)


if __name__=='__main__':unittest.main()

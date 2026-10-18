import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError, URLError
from behavior import channels, EXPRESSIONS, MOTIONS
from quality_profiles import apply_profile
from layer_cache import cached_layer, key_lock
from playback import ResponseGate, state_config
from ai_adapter import chat
from cache_admin import clean_previous
from cache_pipeline import publish,lookup


class BehaviorTests(unittest.TestCase):
    def test_all_behaviors_return_neutral_endpoints_and_bounded_face(self):
        for expression in EXPRESSIONS:
            for motion in MOTIONS:
                for t in [i/24 for i in range(49)]:
                    c=channels(t,2,expression,1,motion,'left')
                    for key in ('smile','surprise','brow','blink'):
                        self.assertTrue(0<=c[key]<=1)
                    if t in (0,2):
                        self.assertTrue(all(abs(v)<1e-8 for v in c.values()))
    def test_gaze_and_motion_are_independent(self):
        left=channels(0.75,2,'smile',0.6,'nod','left')
        right=channels(0.75,2,'smile',0.6,'nod','right')
        self.assertAlmostEqual(left['gaze'],-right['gaze'])
        self.assertEqual(left['pitch'],right['pitch'])
    def test_unknown_profile_and_final_rejected(self):
        for name in ('final','bad'):
            with self.assertRaises(ValueError):apply_profile({},name)
    def test_visible_controls_roundtrip_preserves_existing_cache_identity(self):
        from desktop_controller import selection
        from cache_pipeline import cache_key
        base=selection({'preset':'head-draft'})
        q=base['quality'];p=base['performance']
        again=selection({'preset':'head-draft','settings':dict(profile=q['profile'],width=q['width'],height=q['height'],fps=q['fps'],samples=q['samples'],hair=q['hair'],camera=base['scene']['camera'],frames=p['frames'],expression=p['expression'],motion=p['motion_revision'],strength=0.6,gaze='camera',enter=0.25,leave=0.25)})
        self.assertEqual(cache_key(base),cache_key(again))

    def test_profiles_expand_and_preserve_original(self):
        c={'performance':{'frames':48},'quality':{}}
        a=apply_profile(c,'draft');b=apply_profile(c,'preview')
        self.assertNotEqual(a['quality'],b['quality'])
        self.assertEqual(c['quality'],{})
    def test_all_state_configs_have_same_framing(self):
        configs=[state_config(state) for state in ('idle','listening','thinking')]
        self.assertEqual(len({json.dumps(c['scene'],sort_keys=True) for c in configs}),1)
    def test_state_reel_resamples_frame_clock_without_shortening_speech(self):
        from render_settings import PROJECT
        base=json.loads((PROJECT/'configs/head-draft.json').read_text('utf-8-sig'))
        base['performance']['tts_file']='fixture-only'
        for fps in (24,30):
            for frames in range(2,100):
                base['quality']['fps']=fps;base['performance']['frames']=frames
                with patch('playback.resolve',side_effect=lambda c:c):result=state_config('speaking',speaking=base)
                duration=result['performance']['frames']/24
                self.assertGreaterEqual(duration+1e-9,frames/fps)
                self.assertLess(duration-frames/fps,1/24+1e-9)

    def test_stop_invalidates_pending_response_even_after_completion(self):
        gate=ResponseGate();old=gate.begin();gate.stop()
        self.assertFalse(gate.accepts(old))
        new=gate.begin();self.assertTrue(gate.accepts(new));self.assertFalse(gate.accepts(old))


class LayerTests(unittest.TestCase):
    def test_exact_reuse_and_corruption_regeneration(self):
        with tempfile.TemporaryDirectory() as folder:
            def produce(p):(p/'data').write_bytes(b'good')
            call=Mock(side_effect=produce)
            path,hit=cached_layer(folder,{'text':'hello'},call)
            self.assertFalse(hit)
            self.assertTrue(cached_layer(folder,{'text':'hello'},call)[1])
            self.assertEqual(call.call_count,1)
            (path/'data').write_bytes(b'bad')
            self.assertFalse(cached_layer(folder,{'text':'hello'},call)[1])
            self.assertEqual(call.call_count,2)
    def test_failed_layer_cannot_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            def fail(path):
                (path/'partial').write_text('partial')
                raise ValueError('failed')
            with self.assertRaises(ValueError):cached_layer(folder,{'text':'a'},fail)
            self.assertFalse(any(p.name.startswith('.stage') for p in Path(folder).iterdir()))
    def test_duplicate_process_key_rejected_and_unlocks(self):
        with tempfile.TemporaryDirectory() as folder:
            with key_lock(folder,'abc'):
                with self.assertRaises(ValueError):
                    with key_lock(folder,'abc'):pass
            with key_lock(folder,'abc'):pass
    def test_chat_context_changes_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(chat('你好',folder)[1])
            self.assertTrue(chat('你好',folder)[1])
            self.assertFalse(chat('你好',folder,context=[{'role':'assistant','content':'不同上下文'}])[1])
    def test_clean_previous_preserves_current_and_unrelated(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('a'*64,'a'*64+'.previous-'+'b'*32,'unrelated.previous-x'):
                (root/name).mkdir();(root/name/'video').write_bytes(b'123')
            self.assertEqual(clean_previous(root),3)
            self.assertTrue((root/('a'*64)).exists());self.assertTrue((root/'unrelated.previous-x').exists())
    def test_video_publish_rename_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'input.mp4';source.write_bytes(b'old')
            config={'fixture':1};publish(root/'cache',config,source)
            source.write_bytes(b'new');original=Path.rename
            def rename(path,target):
                if path.name.startswith('.stage-'):raise OSError('disk failure')
                return original(path,target)
            with patch.object(Path,'rename',rename),self.assertRaises(OSError):publish(root/'cache',config,source)
            self.assertEqual(lookup(root/'cache',config).read_bytes(),b'old')


class DeepSeekTests(unittest.TestCase):
    def test_missing_key_fails_without_network(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'DEEPSEEK_API_KEY':''}),patch('ai_adapter.build_opener') as call:
            with self.assertRaises(ValueError):chat('hi',folder,'deepseek')
            call.assert_not_called()
    def test_invalid_secret_format_cannot_leak_in_request_errors(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'DEEPSEEK_API_KEY':'SECRET\nBAD'}),patch('ai_adapter.build_opener') as call:
            with self.assertRaises(ValueError) as error:chat('hi',folder,'deepseek')
            self.assertNotIn('SECRET',str(error.exception));call.assert_not_called()

    def test_valid_response_and_no_secret_in_cache(self):
        payload={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'text':'你好','expression':'smile','motion':'nod'})}}], 'model':'test','usage':{'total_tokens':12}}
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=json.dumps(payload).encode()
        opener=Mock();opener.open.return_value=response
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'DEEPSEEK_API_KEY':'SECRET-TEST'}),patch('ai_adapter.build_opener',return_value=opener):
            result,hit=chat('hi',folder,'deepseek');self.assertEqual(result['text'],'你好')
            self.assertTrue(chat('hi',folder,'deepseek')[1]);self.assertEqual(opener.open.call_count,1)
            request=json.loads(opener.open.call_args.args[0].data)
            self.assertEqual(request['thinking'],{'type':'disabled'})
            self.assertEqual(request['response_format'],{'type':'json_object'})
            for p in Path(folder).rglob('*.json'):self.assertNotIn('SECRET-TEST',p.read_text('utf-8'))
    def test_http_errors_not_retried_or_leaked(self):
        for code in (401,402,429,500):
            with self.subTest(code=code),tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'DEEPSEEK_API_KEY':'secret'}):
                opener=Mock();opener.open.side_effect=HTTPError('url',code,'secret raw error',{},None)
                with patch('ai_adapter.build_opener',return_value=opener),self.assertRaises(ValueError) as err:chat('hi',folder,'deepseek')
                self.assertNotIn('secret',str(err.exception));self.assertEqual(opener.open.call_count,1)
    def test_timeout_not_retried(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'DEEPSEEK_API_KEY':'secret'}):
            opener=Mock();opener.open.side_effect=TimeoutError()
            with patch('ai_adapter.build_opener',return_value=opener),self.assertRaises(ValueError):chat('hi',folder,'deepseek')
            self.assertEqual(opener.open.call_count,1)


class SpeechLayerTests(unittest.TestCase):
    def test_same_text_reuses_audio_and_face_independently_of_video_settings(self):
        import wave
        import math
        from array import array
        from text_pipeline import prepare_speech
        def synthesize(command, **kwargs):
            folder=Path(command[command.index('-Output')+1])
            samples=array('h',[int(3000*math.sin(i*0.1)) for i in range(11025)])
            with wave.open(str(folder/'syllable_00.wav'),'wb') as stream:
                stream.setparams((1,2,22050,0,'NONE','not compressed'));stream.writeframes(samples.tobytes())
            (folder/'voice.json').write_text('{}')
        with tempfile.TemporaryDirectory() as folder,patch('text_pipeline.subprocess.run',side_effect=synthesize) as call:
            a,b,hits=prepare_speech('test',folder)
            self.assertFalse(hits['audio_hit']);self.assertFalse(hits['face_hit'])
            again,b,hits=prepare_speech('test',folder)
            self.assertEqual(a,again);self.assertTrue(hits['audio_hit']);self.assertTrue(hits['face_hit'])
            self.assertEqual(call.call_count,1)
            prepare_speech('changed',folder)
            self.assertEqual(call.call_count,2)
    def test_invalid_behavior_ranges_rejected_before_render(self):
        from render_settings import validate,PROJECT
        base=json.loads((PROJECT/'configs/head-draft.json').read_text('utf-8-sig'))
        for name,value in [('strength',float('nan')),('strength',2),('gaze','up'),('enter',-1),('leave',9)]:
            c=copy.deepcopy(base);c['performance'][name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):validate(c)


class JobIsolationTests(unittest.TestCase):
    def test_gui_workers_use_hidden_console_python_to_preserve_nested_logs(self):
        from desktop_controller import worker_python
        with tempfile.TemporaryDirectory() as folder:
            windowed=Path(folder)/'pythonw.exe';console=Path(folder)/'python.exe'
            windowed.write_bytes(b'fixture');console.write_bytes(b'fixture')
            with patch('desktop_controller.sys.executable',str(windowed)):
                self.assertEqual(worker_python(),str(console))


    def test_response_tasks_use_unique_output_directories(self):
        from desktop_controller import Jobs
        with tempfile.TemporaryDirectory() as folder,patch('desktop_controller.threading.Thread') as threads:
            a=Jobs(folder).start('text',request={'text':'one'})
            b=Jobs(folder).start('text',request={'text':'two'})
            self.assertNotEqual(a['output_dir'],b['output_dir'])
            for job,call in zip((a,b),threads.call_args_list):
                command=call.kwargs['args'][1]
                self.assertEqual(command[command.index('--output')+1],job['output_dir'])


class DesktopResponseTests(unittest.TestCase):
    def test_cache_corrupted_after_refresh_is_rejected_at_play_click(self):
        from desktop_console import Console
        console=Console.__new__(Console)
        console.summary={'hit':True,'media_path':'previously-verified.mp4'}
        console.player=Mock();console.payload=Mock(return_value={});console.status=Mock()
        with patch('desktop_console.selection',return_value={}),patch('desktop_console.cache_status',return_value={'hit':False}) as lookup:
            console.play()
        lookup.assert_called_once();console.player.play.assert_not_called()


    def test_late_answer_after_stop_cannot_play_or_update_context(self):
        import queue
        from desktop_console import Console
        console=Console.__new__(Console)
        console.results=queue.Queue();console.jobs=Mock()
        console.jobs.snapshot.return_value=dict(state='succeeded',kind='answer',stage='starting',elapsed=1,frames_done=0,progress=100,logs=[])
        console.busy=True;console.root=Mock();console.player=Mock();console.log=Mock()
        console.progress={};console.status=Mock();console.context=[{'role':'user','content':'old'}]
        console.variables={'preset':Mock()};console.reload_presets=Mock();console.set_busy=Mock()
        console.gate=ResponseGate();console.reel_token=console.gate.begin();console.waiting_player=True
        console.stop()
        console.poll()
        console.player.play.assert_not_called()
        self.assertEqual(console.context,[{'role':'user','content':'old'}])


if __name__=='__main__':unittest.main()

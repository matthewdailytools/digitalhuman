import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from ai_motion import EXAMPLE, plan_actions
from micro_control import manual_plan, validate_plan, sample_plan
from micro_pipeline import prepare
from render_settings import PROJECT, validate
from cache_pipeline import cache_key


def single(control, value, duration=2):
    return dict(schema_version=1,duration=duration,auto_blink=False,
                events=[dict(control=control,start=0,end=duration,value=value)])


class MicroControlTests(unittest.TestCase):
    def test_independent_channels_and_neutral_endpoints(self):
        mapping={'eye_close':'eye_close','smile':'smile','mouth_open':'mouth_open','nod':'pitch'}
        for control, channel in mapping.items():
            plan=validate_plan(single(control,1))
            peak=sample_plan(plan,1)
            self.assertGreater(peak[channel],0.1)
            self.assertTrue(all(v==0 for k,v in peak.items() if k!=channel))
            for t in (-1,0,2,3):
                self.assertTrue(all(v==0 for v in sample_plan(plan,t).values()))
        gaze=sample_plan(validate_plan(single('gaze',[-1,1])),1)
        self.assertEqual((gaze['gaze_x'],gaze['gaze_y']),(-1,1))

    def test_nod_does_one_down_up_cycle_with_smooth_endpoints(self):
        plan=single('nod',1)
        curve=[sample_plan(plan,i/100)['pitch'] for i in range(201)]
        self.assertTrue(all(x>=0 for x in curve))
        self.assertEqual(curve.index(max(curve)),100)
        self.assertLess(curve[1],0.0001)
        self.assertAlmostEqual(curve[50],curve[150])

    def test_rejects_nonfinite_values_unknown_controls_and_overlaps(self):
        bad=[]
        for control,value in [('execute',1),('smile',2),('eye_close',True),('mouth_open',float('nan')),
                              ('gaze',[float('inf'),0]),('gaze',[0,True])]:
            bad.append(single(control,value))
        plan=single('smile',1);plan['events']*=2;bad.append(plan)
        plan=single('smile',1);plan['events'][0]['end']=3;bad.append(plan)
        plan=single('smile',1);plan['events'][0]['start']=1.9;bad.append(plan)
        plan=single('smile',1);plan['command']='run';bad.append(plan)
        for plan in bad:
            with self.subTest(plan=plan),self.assertRaises(ValueError):validate_plan(plan)

    def test_manual_controls_are_independent_and_not_a_speech_preset(self):
        plan=manual_plan(dict(eye_close=1,smile=0.5,mouth_open=0.8,nod=0.3),[0,-1],2)
        values=sample_plan(plan,1)
        self.assertEqual(values['eye_close'],1)
        self.assertEqual(values['mouth_open'],0.8)
        with tempfile.TemporaryDirectory() as folder:
            request=dict(mode='manual',controls=dict(eye_close=1,smile=0,mouth_open=0,nod=0),gaze=[0,0],duration=2)
            config,status=prepare(request,folder)
            self.assertNotIn('audio_file',config['performance'])
            self.assertEqual(config['performance']['frames'],49)
            self.assertEqual(status['source'],'manual-controls')
            second=copy.deepcopy(config);second['performance']['micro_control']['events'][0]['value']=0
            self.assertNotEqual(cache_key(config),cache_key(second))
            second=copy.deepcopy(config);second['performance']['frames']=24
            with self.assertRaises(ValueError):validate(second)
            second=copy.deepcopy(config);second['performance']['tts_file']='some-file'
            with self.assertRaises(ValueError):validate(second)

    def test_old_configs_still_validate(self):
        validate(json.loads((PROJECT/'configs/head-draft.json').read_text('utf-8-sig')))


class AIMotionTests(unittest.TestCase):
    def test_invalid_quality_rejected_before_billable_plan_request(self):
        with tempfile.TemporaryDirectory() as folder,patch('micro_pipeline.plan_actions') as call:
            with self.assertRaises(ValueError):
                prepare(dict(mode='ai',instruction='test',provider='deepseek',quality={'width':641}),folder)
            call.assert_not_called()


class DesktopMicroResultTests(unittest.TestCase):
    def test_stopped_micro_job_caches_without_autoplay_and_uses_its_own_result(self):
        import queue
        from desktop_console import Console
        from playback import ResponseGate
        for stopped in (False,True):
            with self.subTest(stopped=stopped),tempfile.TemporaryDirectory() as folder:
                output=Path(folder)
                (output/'result.json').write_text(json.dumps(dict(plan=EXAMPLE,source='fixture-ai',video_hit=True)),'utf-8')
                (output/'answer.json').write_text(json.dumps(dict(config={'task':'owned'})),'utf-8')
                console=Console.__new__(Console)
                console.results=queue.Queue();console.jobs=Mock()
                console.jobs.snapshot.return_value=dict(kind='micro',state='succeeded',stage='cache-hit',elapsed=1,
                                                       frames_done=0,progress=100,logs=[],output_dir=str(output))
                console.busy=True;console.root=Mock();console.player=Mock();console.log=Mock()
                console.status=Mock();console.progress={};console.variables={'preset':Mock()}
                console.reload_presets=Mock();console.set_busy=Mock();console.show_plan=Mock()
                console.result_tabs=Mock();console.plan_page=object();console.waiting_player=False
                console.gate=ResponseGate();console.reel_token=console.gate.begin()
                if stopped:console.stop()
                with patch('desktop_console.cache_status',return_value={'hit':True,'media_path':'owned-cache.mp4'}) as lookup:
                    console.poll()
                if stopped:
                    console.player.play.assert_not_called();lookup.assert_not_called()
                else:
                    lookup.assert_called_once_with({'task':'owned'})
                    console.player.play.assert_called_once_with('owned-cache.mp4',False)
                console.show_plan.assert_called_once_with(EXAMPLE)

    def test_structured_ai_plan_is_validated_and_reused_without_another_call(self):
        payload={'choices':[{'finish_reason':'stop','message':{'content':'```json\n'+json.dumps(EXAMPLE)+'\n```'}}],
                 'model':'fixture','usage':{'total_tokens':100}}
        with tempfile.TemporaryDirectory() as folder,patch('ai_motion.request_deepseek',return_value=json.dumps(payload).encode()) as call:
            result,hit=plan_actions('闭眼后微笑',folder,'deepseek')
            self.assertFalse(hit);self.assertEqual(result['source'],'deepseek')
            self.assertTrue(plan_actions('闭眼后微笑',folder,'deepseek')[1])
            call.assert_called_once()
            self.assertEqual(result['plan'],EXAMPLE)

    def test_invalid_or_plain_ai_text_never_becomes_an_executable_plan(self):
        for content in ('你好，我会微笑', json.dumps(single('run_shell',1)), json.dumps(single('smile',99))):
            payload={'choices':[{'finish_reason':'stop','message':{'content':content}}]}
            with tempfile.TemporaryDirectory() as folder,patch('ai_motion.request_deepseek',return_value=json.dumps(payload).encode()) as call:
                with self.assertRaises(ValueError):plan_actions('test',folder,'deepseek')
                call.assert_called_once()
                self.assertFalse(any(Path(folder).glob('*/plan.json')))

    def test_mock_is_explicitly_a_fixed_demo_and_makes_no_network_call(self):
        with tempfile.TemporaryDirectory() as folder,patch('ai_motion.request_deepseek') as call:
            result,_=plan_actions('任意输入',folder)
            self.assertEqual(result['source'],'mock-fixed-demo-not-ai')
            call.assert_not_called()


if __name__=='__main__':unittest.main()

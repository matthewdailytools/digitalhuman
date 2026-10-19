import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from cache_pipeline import cache_key
from micro_pipeline import prepare
from scan_binding import (jaw_weights,blink_delta,hairline,smile_corner_delta,
                          smile_cheek_delta,smile_lid_delta,smile_open_delta)
from scanned_settings import base_config,validate
from desktop_console import Console


class ScannedBindingTests(unittest.TestCase):
    def test_smile_regions_preserve_seam_and_unrelated_anatomy(self):
        for p in ((0,-13,23.8),(0,2,24),(0,-9,38),(0,-3,12)):
            self.assertEqual(smile_corner_delta(p),(0,0,0))
            self.assertEqual(smile_open_delta(p),(0,0,0))
        self.assertGreater(smile_cheek_delta((3.8,-11,26.7))[2],.25)
        self.assertEqual(smile_cheek_delta((3,-11.5,29.8)),(0,0,0))
        positive=smile_corner_delta((2.35,-12,23.8));negative=smile_corner_delta((-2.35,-12,23.8))
        self.assertAlmostEqual(positive[0],-negative[0]);self.assertEqual(positive[1:],negative[1:])

    def test_open_corrective_limits_width_without_erasing_smile_lift(self):
        base=smile_corner_delta((2.35,-12,23.8));fix=smile_open_delta((2.35,-12,23.8))
        self.assertGreater(base[0]+fix[0],0);self.assertLess(base[0]+fix[0],base[0])
        self.assertGreater(base[2]+fix[2],.3)
        eyes=[[3,-9.8,29.8],[-3,-9.8,29.8]]
        self.assertGreater(smile_lid_delta((3,-11.5,29.37),eyes)[2],.02)

    def test_smile_sample_timeline_and_native_dispatch(self):
        from smile_sample import smile_plan
        from micro_control import sample_plan
        plan=smile_plan()
        self.assertEqual(sample_plan(plan,0)['smile'],0)
        self.assertEqual(sample_plan(plan,6)['smile'],0)
        self.assertAlmostEqual(sample_plan(plan,1)['smile'],.35)
        self.assertAlmostEqual(sample_plan(plan,2.5)['smile'],.9)
        self.assertAlmostEqual(sample_plan(plan,4.25)['mouth_open'],.65)
        self.assertEqual(sample_plan(plan,5.125)['eye_close'],1)
        c=Console.__new__(Console);c.busy=False;c.payload=Mock(return_value={'settings':{'fps':8,'text':'stale'}})
        c.micro_character=Mock();c.show_plan=Mock();c.start=Mock();c.status=Mock()
        Console.prepare_smile_sample(c)
        self.assertEqual(c.start.call_args.kwargs['request'],dict(mode='smile-sample',character='scanned-head',quality={'fps':8}))

    def test_sample_requires_scan_and_never_requests_ai(self):
        with tempfile.TemporaryDirectory() as temporary,patch('micro_pipeline.plan_actions') as ai:
            with self.assertRaises(ValueError):prepare(dict(mode='smile-sample'),temporary)
            with patch('scanned_settings.resolve',side_effect=lambda c:c):
                config,status=prepare(dict(mode='smile-sample',character='scanned-head'),temporary)
            self.assertEqual(status['source'],'smile-deformation-sample')
            self.assertEqual(config['performance']['micro_control']['duration'],6)
            ai.assert_not_called()

    def test_nearly_coincident_lips_use_mesh_paths_not_height(self):
        # The upper and lower seam have reversed heights but separate topology paths.
        p=[(0,-13,24),(0,-13,23.5),(3,-12,23.6),(0,-13,23.3),(0,-13,23.6)]
        f=[[0,1,2],[2,3,4]]
        weights=jaw_weights(p,f,0,3)
        self.assertEqual(weights[1],0);self.assertEqual(weights[4],1)

    def test_blink_does_not_move_forehead_mouth_or_back_of_head(self):
        eyes=[[3,-9.8,29.8],[-3,-9.8,29.8]]
        for p in ((0,-9,38),(0,-13,24),(3,3,30)):
            self.assertEqual(blink_delta(p,eyes),(0,0,0))
        self.assertLess(blink_delta((3,-11.55,30.3),eyes)[2],-.5)
        self.assertGreater(blink_delta((3,-11.5,29.37),eyes)[2],.15)
        self.assertGreater(hairline(0,-10),hairline(0,5))

    def test_unsupported_scan_settings_fail_before_ai_or_asset_build(self):
        for quality in ({'hair':'sway'},{'width':641},{'profile':'final'},{'fps':True}):
            with self.subTest(quality=quality),tempfile.TemporaryDirectory() as temporary,patch('micro_pipeline.plan_actions') as ai,patch('scanned_assets.ensure_rig') as asset:
                with self.assertRaises(ValueError):prepare(dict(mode='ai',character='scanned-head',instruction='测试',quality=quality),temporary)
                ai.assert_not_called();asset.assert_not_called()

    def test_scan_manual_plan_is_independent_and_has_distinct_cache_identity(self):
        def resolved(config):
            result=copy.deepcopy(config);result['character']['rig_sha256']='test-asset';return result
        request=dict(mode='manual',character='scanned-head',controls=dict(eye_close=1,smile=0,mouth_open=0,nod=0),gaze=[0,0],duration=1)
        with tempfile.TemporaryDirectory() as temporary,patch('scanned_settings.resolve',side_effect=resolved):
            config,status=prepare(request,temporary)
        self.assertEqual(config['character']['id'],'scanned-head')
        self.assertEqual(status['source'],'manual-controls')
        self.assertEqual(config['performance']['frames'],25)
        other=copy.deepcopy(config);other['quality']['hair']='none'
        self.assertNotEqual(cache_key(config),cache_key(other))
        other=copy.deepcopy(config);other['character']['rig_sha256']='different-asset'
        self.assertNotEqual(cache_key(config),cache_key(other))
        other=copy.deepcopy(config);other['performance']['micro_control']['events'][0]['value']=0
        self.assertNotEqual(cache_key(config),cache_key(other))

    def test_rejects_unknown_fields_and_mixed_speech_on_scan(self):
        config=base_config({})
        for key,value in (('tts_file','file.wav'),('command','run anything')):
            other=copy.deepcopy(config);other['performance'][key]=value
            with self.assertRaises(ValueError):validate(other)

    def test_desktop_dispatches_selected_scan_without_inheriting_speech(self):
        c=Console.__new__(Console);c.busy=False;c.payload=Mock(return_value={'settings':dict(width=640,height=360,fps=24,samples=4,hair='static',camera='head-closeup',text='stale speech')})
        c.micro_character=Mock();c.micro_character.get.return_value='写实扫描头部'
        c.micro_vars={name:Mock() for name in ('eye_close','smile','mouth_open','nod')}
        for v in c.micro_vars.values():v.get.return_value='0'
        c.micro_duration=Mock();c.micro_duration.get.return_value='1'
        c.micro_gaze=Mock();c.micro_gaze.get.return_value='看镜头';c.gaze_values={'看镜头':[0,0]}
        c.show_plan=Mock();c.start=Mock();c.status=Mock()
        Console.prepare_micro(c,False)
        args=c.start.call_args.kwargs['request']
        self.assertEqual(args['character'],'scanned-head');self.assertNotIn('text',args['quality'])


if __name__=='__main__':unittest.main()

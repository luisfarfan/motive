#!/usr/bin/env python3
"""Offline checks only: no processes, capture, socket, app, clocks or FFmpeg."""
import copy
import unittest
from unittest.mock import MagicMock, patch

from h14_collection_helpers import (PHASES, counter_patches, counter_summary, decode_counter, focus_conditions, owned_stop_command,
    unique_owned_tone, validate_fixture, validate_manifest, validate_markers)
from verify_h14_collection import Client, plan


class CollectionTests(unittest.TestCase):
    def test_new_owned_tone_ignores_order_and_rejects_reuse_or_ambiguity(self):
        mine={'id':'audio-2','name':'owned','source':{'kind':'tone'},'muted':False}
        foreign={'id':'audio-1','name':'foreign','source':{'kind':'microphone','device_id':'other'},'muted':False}
        self.assertEqual(unique_owned_tone([foreign,mine],'owned',{'audio-1'}),'audio-2')
        self.assertEqual(unique_owned_tone([mine,foreign],'owned',{'audio-1'}),'audio-2')
        for inputs,prior in [([mine],{'audio-2'}), ([mine,{**mine,'id':'audio-3'}],set()),
                             ([{**mine,'muted':True}],set()), ([{**mine,'source':foreign['source']}],set()),
                             ([mine,{**foreign,'id':'audio-2'}],set())]:
            with self.assertRaises(ValueError):unique_owned_tone(inputs,'owned',prior)

    def setUp(self):
        self.manifest=plan()['manifest']
        self.ready={'event':'ready','pid':222,'window_id':333,'bundle_id':'local.motive.collectionfixture',
            'arm':'default','audio':False,'capture':False,'content_hz':10,'draw_request_hz':30,
            'offscreen_snapshots':False,'global_preferences_changed':False,'counter':{'bits':16,'least_significant_bit':'left',
            'x':24,'y':24,'step_points':36,'width_points':30,'height_points':48,'coordinate_origin':'bottom_left'}}
        self.state={'event':'window_state','pid':222,'window_id':333,'arm':'default','window_class':'NSWindow','window_level':0,
                    'initial_collection_behavior':0,'collection_behavior':0}

    def markers(self):
        return [{'phase':phase,'trial_id':'A1','owner_pid':111,'fixture_pid':222,'window_id':333,
                 'clock':'python.time.monotonic','host_monotonic':70000+i*20,'wall_unix':1700000000+i*20,
                 'observation':'root_observed_focus_after_cua'} for i,phase in enumerate(PHASES)]

    def test_manifest_and_fixture_require_fresh_exact_identity(self):
        validate_manifest(self.manifest);validate_fixture([self.ready,self.state],self.manifest)
        for key,value in [('pid',223),('window_id',334),('arm','join-all')]:
            changed={**self.state,key:value}
            with self.assertRaises(ValueError):validate_fixture([self.ready,changed],self.manifest)
        with self.assertRaises(ValueError):validate_fixture([self.ready,self.ready,self.state],self.manifest)
        with self.assertRaises(ValueError):validate_fixture([self.ready,{**self.state,'collection_behavior':1<<18}],self.manifest)
        bad=copy.deepcopy(self.manifest);bad['fixture']['pid']=True
        with self.assertRaises(ValueError):validate_manifest(bad)
        bad=copy.deepcopy(self.manifest);bad['seconds']=120
        with self.assertRaises(ValueError):validate_manifest(bad)
        bad=copy.deepcopy(self.manifest);bad['version']=True
        with self.assertRaises(ValueError):validate_manifest(bad)

    def test_markers_reject_raw_clock_wrong_phase_and_other_process(self):
        markers=self.markers();validate_markers(markers,self.manifest,True)
        for key,value in [('clock','CLOCK_MONOTONIC_RAW'),('owner_pid',112),('phase','fixture_front')]:
            changed=copy.deepcopy(markers);changed[1][key]=value
            with self.assertRaises(ValueError):validate_markers(changed,self.manifest,True)
        with self.assertRaises(ValueError):validate_markers(markers[:2],self.manifest,True)

    def picture(self,value,boxes):
        result=bytearray([35])*(480*270)
        for bit,(left,top,right,bottom) in enumerate(boxes):
            for y in range(top,bottom):
                for x in range(left,right):result[y*480+x]=255 if value&(1<<bit) else 0
        return result

    def test_little_endian_counter_zero_wrap_and_invalid_background(self):
        boxes=counter_patches((1360,536),(680,268))
        for value in [0,1,2,32768,65535,12345]:self.assertEqual(decode_counter(self.picture(value,boxes),480,boxes),value)
        self.assertIsNone(decode_counter(bytes(480*270),480,boxes))
        self.assertIsNone(decode_counter(bytes([35])*(480*270),480,boxes))
        invalid=self.picture(15,boxes)
        left,top,right,bottom=boxes[2]
        for y in range(top,bottom):
            for x in range(left,right):invalid[y*480+x]=125
        self.assertIsNone(decode_counter(invalid,480,boxes))

    def test_geometry_accepts_only_full_window_or_exact_fixture_content(self):
        self.assertEqual(len(counter_patches((1360,480),(680,268))),16)
        with self.assertRaises(ValueError):counter_patches((1920,1080),(680,268))

    def test_repeated_content_fails_even_when_timestamps_advance(self):
        frozen=[{'pts_s':i/5,'counter':123} for i in range(40)]
        self.assertEqual(counter_summary(frozen)['status'],'FAIL')
        fresh=[{'pts_s':i/5,'counter':(65530+2*i)%65536} for i in range(40)]
        self.assertEqual(counter_summary(fresh)['status'],'PASS')
        missing=[{'pts_s':i/5,'counter':None} for i in range(40)]
        self.assertEqual(counter_summary(missing)['status'],'INCONCLUSIVE')

    def test_jumps_and_invalid_geometry_do_not_become_freshness_pass(self):
        values=[{'pts_s':i/5,'counter':2*i+(200 if i>15 else 0)} for i in range(40)]
        self.assertEqual(counter_summary(values)['status'],'FAIL')
        values=[{'pts_s':i/5,'counter':None if i%2 else 2*i} for i in range(40)]
        self.assertEqual(counter_summary(values)['status'],'INCONCLUSIVE')

    def test_cleanup_refuses_other_attempt_and_cancels_connecting(self):
        active={'attempt_id':7,'native_busy':True,'phase':'active'}
        self.assertEqual(owned_stop_command(active,7),'stop_output_target')
        self.assertEqual(owned_stop_command({**active,'phase':'connecting'},7),'cancel_output_target')
        self.assertEqual(owned_stop_command({**active,'phase':'stopping'},7),'cancel_output_target')
        self.assertIsNone(owned_stop_command({**active,'native_busy':False},7))
        with self.assertRaises(ValueError):owned_stop_command(active,8)

    def test_connected_peer_checked_before_any_mutation_bytes(self):
        client=Client.__new__(Client);client.pid=123;client.socket='/unused';client.out=None
        channel=MagicMock();channel.getsockopt.return_value=999
        context=MagicMock();context.__enter__.return_value=channel
        with patch('verify_h14_collection.socket.socket',return_value=context):
            with self.assertRaises(ValueError):client.call('select_source',window_id=333)
        channel.sendall.assert_not_called()

    def test_focus_needs_contemporaneous_fixture_conditions_in_every_phase(self):
        anchor={'fixture_clock':'NSProcessInfo.systemUptime','host_clock':'python.time.monotonic',
                'fixture_clock_s':88000,'host_before_s':69999.99,'host_after_s':70000.01}
        events=[]
        for second in range(60):
            active=not 20 <= second < 40
            events.append({'event':'window_state','uptime_seconds':88000+second,'app_active':active,
                'key_window':active,'window_visible':True,'window_occlusion_visible':active,
                'on_active_space':True,'app_hidden':False,'miniaturized':False})
        focus=focus_conditions(events,[anchor],self.markers(),70060)
        self.assertEqual(focus['status'],'VERIFIED')
        stale=copy.deepcopy(events)
        for event in stale:event['app_active']=False
        focus=focus_conditions(stale,[anchor],self.markers(),70060)
        self.assertEqual(focus['status'],'NOT_OBSERVED')
        self.assertEqual(focus['phases']['studio_front']['status'],'VERIFIED')
        self.assertEqual(focus['phases']['fixture_front']['reason'],'focus_metadata_mismatch')
        focus=focus_conditions(events,[{**anchor,'fixture_clock':'CLOCK_MONOTONIC_RAW'}],self.markers(),70060)
        self.assertEqual(focus['status'],'NOT_OBSERVED')
        focus=focus_conditions(events[:10],[anchor],self.markers(),70060)
        self.assertEqual(focus['phases']['fixture_return']['status'],'NOT_OBSERVED')
        shifted={**anchor,'host_before_s':70003,'host_after_s':70003.01}
        self.assertEqual(focus_conditions(events,[anchor,shifted],self.markers(),70060)['status'],'NOT_OBSERVED')


if __name__=='__main__':unittest.main()

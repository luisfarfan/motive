#!/usr/bin/env python3
"""Pure validation tests; no owner, socket, GUI, media or physical execution."""
import copy
import json
import pathlib
import unittest

from h14_ui_concurrency_helpers import (classify_result, expected_configuration, pending_evidence,
    temporary_configuration, ui_gain_edit, validate_manifest, validate_saved_project)
from verify_h14_ui_concurrency import plan

ROOT = pathlib.Path(__file__).resolve().parents[1]


class UIConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.pack = json.loads((ROOT/'show-control/examples/packs/matchday.json').read_text())
        self.deck = json.loads((ROOT/'show-control/examples/decks/matchday.json').read_text())
        self.initial = {'active_scene': 'scene-1', 'sources': [
            {'id': 'main', 'name': 'Principal', 'spec': {'kind': 'pattern'}},
            {'id': 'overlay', 'name': 'Overlay', 'spec': {'kind': 'overlay', 'color': 0x33e8b5}}],
            'scenes': [{'id': 'scene-1', 'name': 'Escena principal', 'layers': []}]}
        graph = copy.deepcopy(self.initial)
        for overlay in self.pack['overlays']:
            graph['sources'].append({'id': 's-'+overlay['id'], 'name': 'MATCHDAY · '+overlay['name'],
                'spec': {'kind': 'overlay', 'color': 0x33e8b5}, 'overlay': copy.deepcopy(overlay['definition'])})
        for scene in self.pack['scenes']:
            graph['scenes'].append({'id': 'c-'+scene['id'], 'name': 'MATCHDAY · '+scene['name'], 'layers': [
                {'id': 'l-'+layer['id'], 'source_id': 's-'+layer['overlay_id'],
                 'layouts': {key: copy.deepcopy(layer[key]) for key in ('horizontal', 'vertical')}} for layer in scene['layers']]})
        self.project = {'version': 5, 'variant': 'horizontal', 'audio': 'none', 'capture_window': False,
            'window': None, 'camera': None, 'video': {'version': 1, 'resolution': 'full_hd1080', 'fps': 30,
            'coordinate_space': 'design960'}, 'graph': graph}
        self.bindings = validate_saved_project(self.project, self.pack, self.initial)
        config, deck = expected_configuration(self.pack, self.deck, self.bindings)
        self.saved = {'version': 1, 'project_fingerprint': 'a'*64, 'config': config, 'deck': deck}
        self.job = {'id': 1, 'state': 'awaiting_completion', 'cursor': 0, 'records': [
            {'index': 0, 'operation_id': 'session:animation:1:1', 'code': None}]}
        self.state = {'pid': 7, 'revision': 10, 'last_action': 'cli · set_audio_gain · revisión 10',
            'show_control': {'counters': {'goals': {'type': 'int', 'value': 0}}},
            'audio_mixer': {'monitoring': 'off', 'store': {'inputs': [
                {'id': 'tone-1', 'source': {'kind': 'tone'}, 'muted': False, 'gain_db': -12}]}},
            'overlays': {'runtime': {'animations': {'jobs': [
                {'operation_id': 1, 'phase': 'running', 'started': True, 'widget_triggered': True, 'duration_ms': 450}]}}}}

    def test_manifest_rejects_boolean_pid_and_unreviewed_hash(self):
        value = plan()['manifest']; validate_manifest(value)
        for changed in ({**value, 'version': True}, {**value, 'project_sha256': 'unknown'},
                        {**value, 'owner': {**value['owner'], 'pid': True}}):
            with self.assertRaises(ValueError): validate_manifest(changed)

    def test_project_rejects_capture_assets_and_modified_controlled_definition(self):
        for changed in ('capture', 'asset', 'text', 'layout'):
            project = copy.deepcopy(self.project)
            if changed == 'capture': project['window'] = {'id': 5}
            if changed == 'asset': project['graph']['sources'][2]['spec'] = {'kind': 'image', 'path': '/private.png'}
            if changed == 'text': project['graph']['sources'][2]['overlay']['color'] = 0
            if changed == 'layout': project['graph']['scenes'][1]['layers'][0]['layouts']['horizontal']['width'] = 1
            with self.assertRaises(ValueError): validate_saved_project(project, self.pack, self.initial)

    def test_stock_is_unchanged_custom_changes_only_goal_duration(self):
        original = copy.deepcopy(self.saved)
        stock, stock_deck = temporary_configuration(self.saved, self.pack, self.deck, self.bindings, 450)
        self.assertEqual(stock, self.saved['config']); self.assertEqual(stock_deck, self.saved['deck'])
        custom, _ = temporary_configuration(self.saved, self.pack, self.deck, self.bindings, 3000)
        self.assertEqual(self.saved, original)
        custom['rules'][0]['actions'][0]['animation']['duration_ms'] = 450
        self.assertEqual(custom, original['config'])
        changed = copy.deepcopy(self.saved); changed['config']['rules'][0]['actions'].append({'type': 'sound', 'resource': 'unexpected'})
        with self.assertRaises(ValueError): temporary_configuration(changed, self.pack, self.deck, self.bindings, 3000)

    def test_cli_edit_and_completed_native_cannot_prove_ui_concurrency(self):
        evidence = pending_evidence(self.state, self.job, 'session', 'tone-1', 450)
        self.assertIsNotNone(evidence); self.assertFalse(ui_gain_edit(evidence))
        self.state['audio_mixer']['store']['inputs'][0]['gain_db'] = 0
        self.assertFalse(ui_gain_edit(pending_evidence(self.state, self.job, 'session', 'tone-1', 450)))
        self.state['overlays']['runtime']['animations']['jobs'][0]['phase'] = 'completed'
        self.state['last_action'] = 'UI · set_audio_gain · revisión 11'
        self.assertIsNone(pending_evidence(self.state, self.job, 'session', 'tone-1', 450))
        self.assertEqual(classify_result(evidence, None, self.job, self.state, 0)['status'], 'NOT_OBSERVED')

    def test_missing_receipt_requires_unchanged_counter_and_no_following_record(self):
        before = pending_evidence(self.state, self.job, 'session', 'tone-1', 450)
        self.state['revision'] = 11; self.state['last_action'] = 'UI · set_audio_gain · revisión 11'
        self.state['audio_mixer']['store']['inputs'][0]['gain_db'] = 0
        self.job['state'] = 'needs_reconciliation'; self.job['records'][0]['code'] = 'MISSING_MUTATION_RECEIPT'
        edit = pending_evidence(self.state, self.job, 'session', 'tone-1', 450)
        self.assertEqual(classify_result(before, edit, self.job, self.state, 0)['status'], 'PASS')
        self.state['show_control']['counters']['goals']['value'] = 1
        self.assertEqual(classify_result(before, edit, self.job, self.state, 0)['status'], 'FAIL')
        self.state['show_control']['counters']['goals']['value'] = 0
        self.job['records'].append({'index': 1, 'code': None})
        self.assertEqual(classify_result(before, edit, self.job, self.state, 0)['status'], 'FAIL')
        self.assertEqual(classify_result(None, edit, self.job, self.state, 0)['status'], 'NOT_OBSERVED')

    def test_duration_and_operation_namespace_are_not_inferred(self):
        with self.assertRaises(ValueError): pending_evidence(self.state, self.job, 'session', 'tone-1', 3000)
        with self.assertRaises(AssertionError): pending_evidence(self.state, self.job, 'other-session', 'tone-1', 450)


if __name__ == '__main__': unittest.main()

#!/usr/bin/env python3
"""Offline protocol/cleanup checks. No Motive process or acceptance fixture."""
import copy
import unittest

from verify_h14_memory import cancel_owned_outputs, cpu_interval, remove_owned_videos


class DomainClient:
    """Enforce the existing RemoveSource/RemoveLayer ownership contract only."""
    def __init__(self):
        self.graph = {'sources': [{'id': 'pattern'}, {'id': 'ours'}], 'scenes': [
            {'id': 'original', 'layers': [{'id': 'original-layer', 'source_id': 'pattern'}]},
            {'id': 'owned-scene', 'layers': [{'id': 'owned-layer', 'source_id': 'ours'}]}]}
        self.outputs = {}
        self.operations = []
        self.fail_remove_once = False

    def state(self):
        return copy.deepcopy({'project': {'graph': self.graph}, 'outputs': self.outputs})

    def call(self, operation, **arguments):
        self.operations.append((operation, arguments))
        if operation == 'remove_layer':
            scene = next(s for s in self.graph['scenes'] if s['id'] == arguments['scene_id'])
            scene['layers'] = [layer for layer in scene['layers'] if layer['id'] != arguments['layer_id']]
        elif operation == 'remove_source':
            source = arguments['source_id']
            if any(layer['source_id'] == source for s in self.graph['scenes'] for layer in s['layers']):
                raise AssertionError('SOURCE_IN_USE')
            if self.fail_remove_once:
                self.fail_remove_once = False
                raise RuntimeError('injected transport failure after layer removal')
            self.graph['sources'] = [s for s in self.graph['sources'] if s['id'] != source]
        elif operation != 'cancel_output_target':
            raise AssertionError('Unexpected operation')


class MemoryHarnessTests(unittest.TestCase):
    def test_remove_layer_before_source_preserves_original_graph(self):
        client = DomainClient()
        identifiers = ['ours']
        remove_owned_videos(client, identifiers, 'owned-scene')
        self.assertEqual([op for op, _ in client.operations], ['remove_layer', 'remove_source'])
        self.assertEqual(identifiers, [])
        self.assertEqual(client.graph['sources'], [{'id': 'pattern'}])
        self.assertEqual(client.graph['scenes'][0]['layers'], [{'id': 'original-layer', 'source_id': 'pattern'}])

    def test_foreign_reference_prevents_any_cleanup_mutation(self):
        client = DomainClient()
        client.graph['scenes'][0]['layers'].append({'id': 'foreign-reference', 'source_id': 'ours'})
        identifiers = ['ours']
        with self.assertRaises(AssertionError):
            remove_owned_videos(client, identifiers, 'owned-scene')
        self.assertEqual(client.operations, [])
        self.assertEqual(identifiers, ['ours'])

    def test_partial_removal_keeps_ownership_for_retry(self):
        client = DomainClient()
        client.fail_remove_once = True
        identifiers = ['ours']
        with self.assertRaises(RuntimeError):
            remove_owned_videos(client, identifiers, 'owned-scene')
        self.assertEqual(identifiers, ['ours'])
        remove_owned_videos(client, identifiers, 'owned-scene')
        self.assertEqual(identifiers, [])
        self.assertEqual([op for op, _ in client.operations], ['remove_layer', 'remove_source', 'remove_source'])

    def test_connecting_output_uses_deferred_cancellation(self):
        client = DomainClient()
        client.outputs = {'streaming': {'attempt_id': 7, 'native_busy': True, 'phase': 'connecting'}}
        cancel_owned_outputs(client, {'streaming': 7})
        self.assertEqual(client.operations, [('cancel_output_target', {'target': 'streaming'})])

    def test_replaced_or_quiescent_output_is_never_stopped(self):
        client = DomainClient()
        client.outputs = {'recording': {'attempt_id': 9, 'native_busy': True}}
        with self.assertRaises(AssertionError):
            cancel_owned_outputs(client, {'recording': 8})
        self.assertEqual(client.operations, [])
        client.outputs['recording']['native_busy'] = False
        cancel_owned_outputs(client, {'recording': 9})
        self.assertEqual(client.operations, [])

    def test_cpu_uses_monotonic_process_deltas_and_rejects_resets(self):
        first = {'monotonic_ns': 1_000_000_000, 'cpu': {
            'available': True, 'user_seconds': 2., 'system_seconds': 1.}}
        last = {'monotonic_ns': 3_000_000_000, 'cpu': {
            'available': True, 'user_seconds': 3., 'system_seconds': 1.5}}
        self.assertEqual(cpu_interval(first, last), 75.)
        self.assertIsNone(cpu_interval(last, first))
        self.assertIsNone(cpu_interval(first, first))
        self.assertIsNone(cpu_interval(None, last))
        last['cpu']['available'] = False
        self.assertIsNone(cpu_interval(first, last))


if __name__ == '__main__':
    unittest.main()

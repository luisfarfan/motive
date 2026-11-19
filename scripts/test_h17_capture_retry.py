"""Offline contract: the explicitly requested recovery attempt stays bounded."""
import json
import unittest

from verify_h14_capture import select_replacement


class Client:
    def __init__(self, results, pid=42):
        self.results = list(results)
        self.pid = pid
        self.selections = []

    def rpc(self, method, params):
        assert method == 'tools/call'
        self.selections.append(params)
        value = self.results.pop(0)
        return {'isError': not value['ok'], 'content': [{'text': json.dumps(value)}]}

    def call(self, op):
        assert op == 'devices'
        return {'devices': {'windows': [{'id': 101, 'pid': self.pid, 'test': True}]}}


READY = {'ok': True}
NOT_READY = {'ok': False, 'error': {'code': 'CAPTURE_NOT_READY'}}


class CaptureRetry(unittest.TestCase):
    def test_default_does_not_retry_rejection(self):
        client, attempts = Client([NOT_READY, READY]), []
        self.assertEqual(select_replacement(client, 101, 42, attempts), NOT_READY)
        self.assertEqual(len(client.selections), 1)

    def test_success_does_not_retry(self):
        client, attempts = Client([READY]), []
        self.assertEqual(select_replacement(client, 101, 42, attempts, True), READY)
        self.assertEqual(len(client.selections), 1)

    def test_single_explicit_retry_preserves_rejection(self):
        client, attempts = Client([NOT_READY, READY]), []
        self.assertEqual(select_replacement(client, 101, 42, attempts, True), READY)
        self.assertEqual([a['response'] for a in attempts], [NOT_READY, READY])
        self.assertEqual(client.selections[0], client.selections[1])

    def test_repeated_not_ready_stops_after_two(self):
        client, attempts = Client([NOT_READY, NOT_READY, READY]), []
        self.assertEqual(select_replacement(client, 101, 42, attempts, True), NOT_READY)
        self.assertEqual(len(client.selections), 2)

    def test_unrelated_failure_never_retries(self):
        failed = {'ok': False, 'error': {'code': 'SOURCE_CREATE_FAILED'}}
        client, attempts = Client([failed, READY]), []
        self.assertEqual(select_replacement(client, 101, 42, attempts, True), failed)
        self.assertEqual(len(client.selections), 1)

    def test_changed_owner_rejects_before_second_selection(self):
        client, attempts = Client([NOT_READY, READY], pid=43), []
        with self.assertRaises(AssertionError):
            select_replacement(client, 101, 42, attempts, True)
        self.assertEqual(len(client.selections), 1)


if __name__ == '__main__':
    unittest.main()

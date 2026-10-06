import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.read_sta_state import Failure
from tools.sta_ipv6_probe import IPv6Probe, scoped


class IPv6Tests(unittest.TestCase):
    def test_only_measured_link_local_scopes_are_allowed(self):
        self.assertEqual(scoped('fe80::1%7', 7), 'fe80::1%7')
        self.assertEqual(scoped('fe80::2', 14), 'fe80::2%14')
        for address, interface in [('fe80::1%14', 7), ('2001:db8::1', 7),
                                   ('192.168.0.1', 7), ('fe80::1%7%14', 7),
                                   ('fe80::1', 15), ('$(command)', 7)]:
            with self.assertRaises(Failure):
                scoped(address, interface)

    def test_ping_binds_both_source_and_destination_and_does_not_publish_endpoints(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, b'Reply from fe80::3%7: time<1ms\n', b'')
        with tempfile.TemporaryDirectory() as directory, patch('tools.sta_ipv6_probe.ROOT', Path(directory)):
            probe = IPv6Probe('fe80::1%7', 'fe80::2%14', 'fe80::3%14', runner=runner)
            result = probe.enabled()
            self.assertTrue(result['ethernet_reply'])
            self.assertEqual(calls[0][1:], ['-6', '-S', 'fe80::1%7', '-n', '2', '-w', '1000', 'fe80::3%7'])
            self.assertNotIn('fe80', json.dumps(result))
            self.assertEqual(len(list((Path(directory) / 'local-evidence').glob('*.txt'))), 1)

    def test_zero_exit_unreachable_or_wrong_peer_are_not_success(self):
        for output in [b'Reply from fe80::1%7: Destination host unreachable\n',
                        b'Reply from fe80::4%7: time=1ms\n',
                        b'Pinging fe80::3%7 with 32 bytes\nRequest timed out\n']:
            with tempfile.TemporaryDirectory() as directory, patch('tools.sta_ipv6_probe.ROOT', Path(directory)):
                def runner(args, **kwargs):
                    return subprocess.CompletedProcess(args, 0, output, b'')
                probe = IPv6Probe('fe80::1%7', 'fe80::2%14', 'fe80::3%14', runner=runner)
                self.assertFalse(probe.ping_once('ethernet', 'before'))

    def test_ping_failure_is_bounded_and_exception_text_is_not_exposed(self):
        with tempfile.TemporaryDirectory() as directory, patch('tools.sta_ipv6_probe.ROOT', Path(directory)):
            def runner(args, **kwargs):
                raise subprocess.TimeoutExpired('SECRET', 8)
            probe = IPv6Probe('fe80::1%7', 'fe80::2%14', 'fe80::3%14', runner=runner)
            with self.assertRaisesRegex(Failure, '^scoped IPv6 measurement failed$'):
                probe.ping_once('ethernet', 'before')

import json
import unittest
from unittest.mock import patch
from tools.read_sta_diagnostics import SYSLOG, collect, summarize_log
from tools.read_sta_state import Failure, LOGOUT
from tests.test_probe_sta_config import Device, PlainProtocol


class DiagnosticTests(unittest.TestCase):
    def test_log_summary_never_copies_text_or_identifiers(self):
        result = summarize_log([{'content': 'wifix authentication failed secret-ssid 12:34:56:78:90:ab'},
                                {'content': 'ordinary event'}, {'content': ['unexpected']}])
        self.assertEqual(result['wifi_error_rows'], 1)
        self.assertEqual(result['content_rows'], 2)
        self.assertNotIn('secret-ssid', json.dumps(result))
        self.assertNotIn('12:34', json.dumps(result))
        with self.assertRaises(Failure):
            summarize_log({'unexpected': 'secret'})

    def test_diagnostic_failure_logs_out_without_settings_writes(self):
        class LogDevice(Device):
            def post(self, route, payload, token=''):
                if route == '/admin/syslog?form=filter':
                    return {'success': True, 'data': {'type': 'ALL', 'level': 'ALL'}}
                if route == SYSLOG:
                    self.assert_load = payload == b'operation=load'
                    raise Failure('HTTP response rejected')
                return super().post(route, payload, token)
        device = LogDevice()
        with patch('tools.read_sta_diagnostics.login_session', return_value=(PlainProtocol(), 'token')):
            result = collect(device, None, lambda: 'secret')
        self.assertEqual(result['outcome'], 'stopped')
        self.assertEqual(result['logout'], 'complete')
        self.assertTrue(device.assert_load)
        self.assertEqual(device.writes, [])

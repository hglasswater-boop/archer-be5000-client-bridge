import json
import unittest
from unittest.mock import patch
from tools.read_sta_diagnostics import SYSLOG, MESH, collect, summarize_log, mesh_observation, summarize_survey, radio_observation
from tools.probe_sta_config import request
from tools.read_sta_state import Failure, LOGOUT
from tests.test_probe_sta_config import Device, PlainProtocol


class DiagnosticTests(unittest.TestCase):
    def test_radio_read_omits_credentials_and_unknown_values(self):
        result = radio_observation({'wireless_5g_enable': 'on', 'radio_5g_channel': '36',
                                    'wireless_5g_ssid': 'private', 'radio_5g_mode': 'private'})
        self.assertEqual(result['radio_5g_channel'], 36)
        self.assertNotIn('private', json.dumps(result))
    def test_survey_matches_saved_target_without_identifiers(self):
        self.assertEqual(summarize_survey({}, 'private')['rows'], 0)
        rows = [{'ssid': 'private', 'bssid': '00:11:22:33:44:55', 'channel': 36,
                 'signal': 70, 'encryption': 'psk_sae', 'psk_version': 'sae_transition'},
                {'ssid': 'other', 'channel': 44}]
        result = summarize_survey(rows, 'private')
        self.assertEqual(result['target_matches'], 1)
        self.assertEqual(result['targets'][0]['channel'], 36)
        self.assertNotIn('private', json.dumps(result))
        self.assertNotIn('00:11', json.dumps(result))
        with self.assertRaises(Failure):
            summarize_survey({'secret': 'private'}, 'private')

    def test_mesh_getter_sanitizes_and_cannot_be_used_as_setter(self):
        self.assertEqual(mesh_observation({'enable': 'on', 'secret': 'private'}), {'enable': 'on'})
        self.assertEqual(mesh_observation({'enable': 'private'}), {'enable': 'unavailable'})
        with self.assertRaises(Failure):
            request(None, None, '', MESH, 'write', {'enable_5g': 'off'})

    def test_optional_mesh_read_preserves_active_sta_and_logs_out_on_later_failure(self):
        class MeshDevice(Device):
            def post(self, route, payload, token=''):
                if route == MESH:
                    self.mesh_read_only = payload == b'operation=read'
                    return {'success': True, 'data': {'enable': 'on', 'identifier': 'private'}}
                if route == '/admin/syslog?form=filter':
                    raise Failure('HTTP response rejected')
                return super().post(route, payload, token)
        device = MeshDevice()
        device.state['enable_5g'] = 'on'
        with patch('tools.read_sta_diagnostics.login_session', return_value=(PlainProtocol(), 'token')):
            result = collect(device, None, lambda: 'secret', probe_mesh=True)
        self.assertEqual(result['mesh_setting'], {'enable': 'on'})
        self.assertTrue(device.mesh_read_only)
        self.assertEqual(device.writes, [])
        self.assertEqual(device.state['enable_5g'], 'on')
        self.assertEqual(result['logout'], 'complete')
        self.assertNotIn('private', json.dumps(result))

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

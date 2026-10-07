import unittest
import json
from urllib.parse import parse_qs
from unittest.mock import patch
from tools.configure_converter import configure, mesh_off, ap_off
from tools.read_sta_state import Failure
from tests.test_probe_sta_config import Device, PlainProtocol
from tools.read_sta_diagnostics import MESH


class ConverterTests(unittest.TestCase):
    def test_ap_off_explicitly_prevents_controller_radio_disable_completion(self):
        class APDevice:
            def post(self, route, payload, token):
                self.fields = parse_qs(payload.decode())
                return {'success': True, 'data': {}}
        device = APDevice()
        ap_off(device, PlainProtocol(), 'token', '5g')
        self.assertEqual(device.fields, {'operation': ['write'], 'form': ['wireless_5g'],
                                        'wireless_5g_enable': ['off'], 'wireless_5g_disabled_all': ['off']})
        with self.assertRaises(Failure):
            ap_off(device, PlainProtocol(), 'token', '6g')
    def test_mesh_off_and_sta_reapply_keep_state_without_restore(self):
        class MeshDevice(Device):
            mesh = 'on'
            def post(self, route, payload, token=''):
                if route == MESH:
                    fields = parse_qs(payload.decode())
                    if fields.get('operation') == ['write']:
                        self.mesh = fields['enable'][0]
                    return {'success': True, 'data': {'enable': self.mesh}}
                return super().post(route, payload, token)
        device = MeshDevice()
        device.state.update(enable_5g='on', ssid_5g='PRIVATE', psk_key_5g='WiFiTestSecret')
        with patch('tools.configure_converter.login_session', return_value=(PlainProtocol(), 'token')):
            result = configure(device, None, lambda: 'secret', sleep=lambda _: None)
        self.assertEqual(result['outcome'], 'mesh-off-sta-retained')
        self.assertEqual(device.mesh, 'off')
        self.assertEqual(len(device.writes), 1)
        self.assertEqual(device.state['enable_5g'], 'on')
        self.assertEqual(result['logout'], 'complete')
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('WiFiTestSecret', json.dumps(result))

    def test_mesh_off_uses_exact_normal_setting_request(self):
        class MeshDevice:
            def post(self, route, payload, token):
                self.call = (route, payload)
                return {'success': True, 'data': {'enable': 'off'}}
        device = MeshDevice()
        mesh_off(device, PlainProtocol(), 'token')
        self.assertEqual(device.call, (MESH, b'operation=write&enable=off'))

    def test_invalid_management_precondition_prevents_mesh_write(self):
        device = Device(dhcp='on')
        device.state['enable_5g'] = 'on'
        with patch('tools.configure_converter.login_session', return_value=(PlainProtocol(), 'token')):
            result = configure(device, None, lambda: 'secret', sleep=lambda _: None)
        self.assertEqual(result['outcome'], 'stopped')
        self.assertFalse(result.get('mesh_write_attempted', False))
        self.assertEqual(device.writes, [])
        self.assertEqual(result['logout'], 'complete')

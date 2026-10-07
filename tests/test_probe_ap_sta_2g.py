import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from tests.test_probe_sta_config import Device, PlainProtocol
from tools.connect_sta_2g import plan_2g
from tools.probe_ap_sta_2g import RADIO, probe
from tools.read_sta_diagnostics import MESH
from tools.read_sta_state import Failure


class ApDevice(Device):
    def __init__(self, fail_on=False):
        super().__init__()
        self.state.update(plan_2g('nisin2.4', 'TestWiFiKey'))
        self.ap = {'wireless_2g_enable': 'off', 'wireless_2g_disabled_all': 'off', 'wireless_2g_channel': '5'}
        self.ap_writes = []
        self.mesh = 'off'
        self.mesh_writes = []
        self.fail_on = fail_on

    def post(self, route, payload, token=''):
        fields = {k: v[0] for k, v in parse_qs(payload.decode()).items()}
        if route == RADIO:
            if fields['operation'] == 'write':
                self.ap_writes.append(fields)
                self.ap.update({k: v for k, v in fields.items() if k.startswith('wireless_2g_')})
                if self.fail_on and fields['wireless_2g_enable'] == 'on':
                    raise Failure('management network request failed')
            return {'success': True, 'data': self.ap.copy()}
        if route == '/admin/wireless?form=wireless_5g':
            return {'success': True, 'data': {'wireless_5g_enable': 'off', 'wireless_5g_disabled_all': 'off'}}
        if route == MESH:
            if fields['operation'] == 'write':
                self.mesh_writes.append(fields['enable'])
                self.mesh = fields['enable']
            return {'success': True, 'data': {'enable': self.mesh}}
        return super().post(route, payload, token)


class ApStartTests(unittest.TestCase):
    def run_probe(self, device, **kwargs):
        with patch('tools.probe_ap_sta_2g.login_session', return_value=(PlainProtocol(), 'token')), patch('tools.probe_ap_sta_2g.observe_authenticated'):
            return probe(device, None, lambda: 'test-admin', sleep=lambda s: None, **kwargs)

    def test_success_turns_ap_off_and_preserves_active_sta(self):
        device = ApDevice()
        report = self.run_probe(device)
        self.assertEqual(report['outcome'], 'ap-start-comparison-complete')
        self.assertEqual([r['wireless_2g_enable'] for r in device.ap_writes], ['on', 'off'])
        self.assertTrue(all(r['wireless_2g_disabled_all'] == 'off' for r in device.ap_writes))
        self.assertEqual(report['ap_off'], 'verified')
        self.assertTrue(report['sta_fields_preserved_after_ap_off'])
        self.assertEqual(device.state['enable_2g'], 'on')
        self.assertEqual(report['logout'], 'complete')
        self.assertNotIn('TestWiFiKey', json.dumps(report))

    def test_lost_ap_on_response_still_turns_ap_off(self):
        device = ApDevice(fail_on=True)
        report = self.run_probe(device)
        self.assertEqual(report['outcome'], 'stopped')
        self.assertEqual(report['ap_off'], 'verified')
        self.assertEqual(device.ap['wireless_2g_enable'], 'off')
        self.assertEqual(device.state['enable_2g'], 'on')
        self.assertEqual(report['logout'], 'complete')

    def test_baseline_mismatch_stops_without_ap_write(self):
        device = ApDevice()
        device.ap['wireless_2g_channel'] = 'auto'
        report = self.run_probe(device)
        self.assertEqual(report['outcome'], 'stopped')
        self.assertEqual(device.ap_writes, [])
        self.assertEqual(report['logout'], 'complete')

    def test_changed_parent_channel_is_checked_against_retained_radio(self):
        device = ApDevice()
        device.ap['wireless_2g_channel'] = '4'
        report = self.run_probe(device, target_channel=4)
        self.assertEqual(report['target_channel'], 4)
        self.assertEqual(report['outcome'], 'ap-start-comparison-complete')
        self.assertEqual(report['ap_off'], 'verified')

    def test_scan_failure_during_trial_still_turns_ap_off(self):
        device = ApDevice()
        def fail_scan(ssid):
            raise Failure('PC scan failed')
        report = self.run_probe(device, scan_observer=fail_scan)
        self.assertEqual(report['outcome'], 'stopped')
        self.assertEqual(report['ap_off'], 'verified')
        self.assertEqual(device.state['enable_2g'], 'on')
        self.assertEqual(report['logout'], 'complete')

    def test_restart_failure_reenables_sta_before_finishing(self):
        device = ApDevice()
        device.lose_write_response = True
        report = self.run_probe(device, restart_sta=True)
        self.assertEqual(report['outcome'], 'stopped')
        self.assertTrue(report['sta_on_recovery_verified'])
        self.assertEqual(device.state['enable_2g'], 'on')
        self.assertEqual(report['ap_off'], 'verified')
        self.assertEqual(report['logout'], 'complete')

    def test_mesh_comparison_returns_mesh_and_ap_off_with_sta_on(self):
        device = ApDevice()
        report = self.run_probe(device, restart_sta=True, probe_mesh_start=True)
        self.assertEqual(device.mesh_writes, ['on', 'off'])
        self.assertTrue(report['mesh_off_verified'])
        self.assertTrue(report['ap_5g_off_verified'])
        self.assertTrue(report['sta_on_recovery_verified'])
        self.assertEqual(report['ap_off'], 'verified')
        self.assertEqual(device.state['enable_2g'], 'on')

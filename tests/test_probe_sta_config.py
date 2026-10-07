import copy
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from tools.probe_sta_config import (FIELDS, STA, STATUS, connection_plan, main, original_state,
                                   probe, request, status_observation)
from tools.read_sta_state import Failure, LOGOUT

INITIAL = {'enable_2g': 'off', 'enable_5g': 'off', 'ssid_5g': '', 'psk_key_5g': '',
           'encryption_5g': 'psk', 'psk_version_5g': 'rsn', 'psk_cipher_5g': 'aes',
           'wds_mode_5g': '2', 'locktoap_5g': 'off'}


class PlainProtocol:
    def encrypt(self, data):
        return data.encode()

    def decrypt(self, data):
        return data


class Device:
    def __init__(self, *, dhcp='off', fail_write=False, lose_write_response=False, fail_restore=False):
        self.cookie = 'own-test-session'
        self.state = copy.deepcopy(INITIAL)
        self.dhcp = dhcp
        self.calls = []
        self.writes = []
        self.fail_write = fail_write
        self.lose_write_response = lose_write_response
        self.fail_restore = fail_restore

    def post(self, route, payload, token=''):
        fields = {k: v[0] for k, v in parse_qs(payload.decode(), keep_blank_values=True).items()}
        self.calls.append((route, fields))
        if route.startswith('/device_config'):
            data = {'certification': ['SG CLS L1 STAGE2'], 'supportJPFeatures': True,
                    'supportOperationMode': ['router', 'ap']}
        elif route.endswith('form=sysmode'):
            data = {'mode': 'router'}
        elif route.endswith('form=lan_ipv4'):
            data = {'ipaddr': '192.168.1.1'}
        elif route.endswith('form=setting'):
            data = {'enable': self.dhcp}
        elif route == LOGOUT:
            data = {}
        elif route == STA:
            if fields['operation'] == 'write':
                self.writes.append(fields.copy())
                if self.fail_write and len(self.writes) == 1:
                    raise Failure('write failed: unrecognized response')
                if self.fail_restore and len(self.writes) == 3:
                    raise Failure('write failed: unrecognized response')
                self.state.update({k: v for k, v in fields.items() if k != 'operation'})
                if self.lose_write_response and len(self.writes) == 1:
                    raise Failure('network request or JSON response failed')
                data = {}
            else:
                data = self.state.copy()
        elif route == STATUS:
            data = {'connect_status': 'connected' if self.state['enable_5g'] == 'on' else 'disconnected'}
        else:
            raise AssertionError(route)
        return {'success': True, 'data': data}


class ProbeTests(unittest.TestCase):
    def run_probe(self, device, **kwargs):
        with patch('tools.probe_sta_config.login_session', return_value=(PlainProtocol(), 'own-token')):
            return probe(device, None, lambda: 'AdminTestSecret',
                         lambda: ('TEST_SSID', 'WiFiTestSecret'), sleep=lambda seconds: None,
                         observe=kwargs.pop('observe', lambda: None), **kwargs)

    def test_success_changes_only_six_fields_and_verifies_full_rollback(self):
        device = Device()
        result = self.run_probe(device)
        self.assertEqual(result['outcome'], 'configuration-probe-complete')
        self.assertEqual(result['rollback'], 'verified')
        self.assertEqual(result['logout'], 'complete')
        self.assertEqual(device.state, INITIAL)
        self.assertEqual(len(device.writes), 3)
        self.assertEqual(set(device.writes[0]) - {'operation'}, set(FIELDS))
        self.assertEqual(device.writes[1], {'operation': 'write', 'enable_5g': 'off'})
        self.assertEqual(result['association'], 'not-measured')
        self.assertEqual(result['forwarding'], 'not-measured')
        self.assertEqual(result['status_after_write'], {'field': 'connect_status', 'value': 'connected'})
        self.assertEqual(result['status_after_restore'], {'field': 'connect_status', 'value': 'disconnected'})
        for secret in ('TEST_SSID', 'WiFiTestSecret', 'AdminTestSecret', 'own-token'):
            self.assertNotIn(secret, json.dumps(result))

    def test_dhcp_on_stops_before_network_password_and_write(self):
        device = Device(dhcp='on')
        with patch('tools.probe_sta_config.login_session', return_value=(PlainProtocol(), 'own-token')):
            result = probe(device, None, lambda: 'AdminTestSecret',
                           lambda: self.fail('must not prompt'), sleep=lambda seconds: None)
        self.assertFalse(result['write_attempted'])
        self.assertEqual(device.writes, [])
        self.assertEqual(result['logout'], 'complete')

    def test_unsafe_credentials_or_unsupported_baseline_are_not_overwritten(self):
        for key, value in [('ssid_5g', 'has space'), ('psk_key_5g', '********'),
                           ('wds_mode_5g', '1'), ('enable_2g', 'on')]:
            device = Device()
            device.state[key] = value
            result = self.run_probe(device)
            self.assertFalse(result['write_attempted'])
            self.assertEqual(device.writes, [])
            if key in ('ssid_5g', 'psk_key_5g'):
                self.assertNotIn(value, json.dumps(result))

    def test_disabled_sta_with_saved_credentials_restores_them_without_reporting_them(self):
        device = Device()
        device.state.update(ssid_5g='OriginalSSID', psk_key_5g='OriginalSecret')
        original = device.state.copy()
        result = self.run_probe(device)
        self.assertEqual(result['rollback'], 'verified')
        self.assertEqual(device.state, original)
        for secret in ('OriginalSSID', 'OriginalSecret', 'WiFiTestSecret'):
            self.assertNotIn(secret, json.dumps(result))

    def test_rejected_or_lost_write_still_disables_and_restores_without_retry(self):
        for device in (Device(fail_write=True), Device(lose_write_response=True)):
            result = self.run_probe(device)
            self.assertEqual(result['outcome'], 'stopped')
            self.assertEqual(result['rollback'], 'verified')
            self.assertEqual(device.state, INITIAL)
            self.assertEqual(len(device.writes), 3)

    def test_interrupt_in_observation_runs_rollback(self):
        def interrupt():
            raise KeyboardInterrupt()
        device = Device()
        result = self.run_probe(device, observe=interrupt)
        self.assertEqual(result['rollback'], 'verified')
        self.assertEqual(device.state, INITIAL)
        self.assertEqual(result['outcome'], 'stopped')

    def test_restore_failure_keeps_disabled_status_distinct_from_full_rollback(self):
        device = Device(fail_restore=True)
        result = self.run_probe(device)
        self.assertEqual(result['rollback'], 'failed')
        self.assertTrue(result['sta_disabled'])
        self.assertEqual(result['logout'], 'complete')
        self.assertNotIn('WiFiTestSecret', json.dumps(result))

    def test_shell_metacharacters_and_other_setters_are_rejected(self):
        for ssid, psk in [('test;cmd', 'WiFiTestSecret'), ('test', '$(command)'),
                          ('test', 'short'), ('test', 'has space')]:
            with self.assertRaises(Failure):
                connection_plan(ssid, psk)
        for route, fields in [('/admin/system?form=sysmode', {'enable_5g': 'on'}),
                               (STA, {'mode': 'client'}), (STA, {})]:
            with self.assertRaises(Failure):
                request(None, None, '', route, 'write', fields)

    def test_transition_security_mapping_is_explicit(self):
        plan = connection_plan('MLO candidate', 'WiFiTestSecret', 'wpa3-transition')
        self.assertEqual(plan['encryption_5g'], 'psk_sae')
        self.assertEqual(plan['psk_version_5g'], 'sae_transition')
        self.assertEqual(plan['psk_cipher_5g'], 'aes')
        with self.assertRaises(Failure):
            connection_plan('test', 'WiFiTestSecret', 'wpa3-only-unknown')

    def test_status_observation_uses_fixed_labels_only(self):
        self.assertEqual(status_observation({'connect_status': 'connected'}),
                         {'field': 'connect_status', 'value': 'connected'})
        self.assertEqual(status_observation({'connected_5g': True}),
                         {'field': 'connected_5g', 'value': 'on'})
        self.assertEqual(status_observation({'status_5g': 'private'}),
                         {'field': 'status_5g', 'value': 'present'})
        self.assertEqual(status_observation({'ssid_5g': 'PRIVATE'}), {'field': 'unavailable'})

    def test_plan_mode_does_not_connect_or_prompt(self):
        with patch('tools.probe_sta_config.Transport') as transport:
            self.assertEqual(main([]), 0)
            transport.assert_not_called()

    def test_ipv6_is_measured_only_inside_the_correct_sta_phase(self):
        device = Device()
        phases = []
        case = self
        class Observer:
            def before(self):
                case.assertEqual(device.state['enable_5g'], 'off')
                phases.append('before')
                return {'ethernet_reply': False, 'wifi_control_reply': True}
            def enabled(self):
                case.assertEqual(device.state['enable_5g'], 'on')
                phases.append('enabled')
                return {'ethernet_reply': True}
            def after(self):
                case.assertEqual(device.state['enable_5g'], 'off')
                phases.append('after')
                return {'ethernet_reply': False}
        result = self.run_probe(device, ipv6=Observer())
        self.assertEqual(phases, ['before', 'enabled', 'after'])
        self.assertTrue(result['ipv6_enabled']['ethernet_reply'])
        self.assertEqual(result['rollback'], 'verified')

    def test_ipv4_observation_failure_still_restores_and_logs_out(self):
        device = Device()
        case = self
        class Observer:
            def before(self):
                case.assertEqual(device.state['enable_5g'], 'off')
                return {'wifi_control': True}
            def enabled(self):
                case.assertEqual(device.state['enable_5g'], 'on')
                raise Failure('DHCP socket observation failed')
            def after(self):
                case.assertEqual(device.state['enable_5g'], 'off')
                return {'offer_on_requested_interface': False}
        result = self.run_probe(device, ipv4=Observer())
        self.assertEqual(result['outcome'], 'stopped')
        self.assertEqual(result['rollback'], 'verified')
        self.assertEqual(result['logout'], 'complete')
        self.assertEqual(device.state, INITIAL)

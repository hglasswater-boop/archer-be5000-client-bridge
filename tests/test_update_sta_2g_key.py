import unittest
import json
from contextlib import ExitStack
from unittest.mock import patch
from tools import update_sta_2g_key
from tools.connect_sta_2g import plan_2g
from tests.test_probe_sta_config import Device, PlainProtocol
from tools.update_sta_2g_key import channel_plan
from tools.read_sta_state import Failure


class ChannelPlanTests(unittest.TestCase):
    def run_key_update(self, device):
        with ExitStack() as stack:
            mocks = {}
            values = {'shutil.which': 'node', 'sys.stdin.isatty': True,
                'sys.stderr.isatty': True, 'Transport': device,
                'login_session': (PlainProtocol(), 'own-token'),
                'getpass.getpass': 'NewTestWiFiKey', 'time.sleep': None,
                'observe_authenticated': {}, 'write_report': None}
            for name, value in values.items():
                mocks[name] = stack.enter_context(patch('tools.update_sta_2g_key.' + name, return_value=value))
            stack.enter_context(patch('sys.argv', ['update_sta_2g_key']))
            stack.enter_context(patch('builtins.print'))
            observer = stack.enter_context(patch('tools.update_sta_2g_key.DhcpObserver'))
            observer.return_value.before.return_value = {'ethernet': {'offer_on_requested_interface': False}}
            result = update_sta_2g_key.main()
            return result, mocks['write_report'].call_args.args[1]

    def test_key_update_reads_back_without_copying_key_or_restoring_sta(self):
        device = Device()
        device.state.update(plan_2g('nisin2.4', 'OldTestWiFiKey'))
        code, report = self.run_key_update(device)
        self.assertEqual(code, 0)
        self.assertFalse(report['key_already_matched'])
        self.assertTrue(report['configuration_verified'])
        self.assertEqual(len(device.writes), 1)
        self.assertEqual(device.state['enable_2g'], 'on')
        self.assertEqual(device.state['psk_key_2g'], 'NewTestWiFiKey')
        self.assertEqual(report['logout'], 'complete')
        self.assertNotIn('TestWiFiKey', json.dumps(report))

    def test_key_write_failure_logs_out_and_does_not_disable_sta(self):
        device = Device(fail_write=True)
        device.state.update(plan_2g('nisin2.4', 'OldTestWiFiKey'))
        code, report = self.run_key_update(device)
        self.assertEqual(code, 1)
        self.assertEqual(len(device.writes), 1)
        self.assertEqual(device.state['enable_2g'], 'on')
        self.assertEqual(report['logout'], 'complete')

    def test_unexpected_ssid_stops_before_key_write(self):
        device = Device()
        device.state.update(plan_2g('OtherTarget', 'OldTestWiFiKey'))
        code, report = self.run_key_update(device)
        self.assertEqual(code, 1)
        self.assertEqual(device.writes, [])
        self.assertEqual(report['logout'], 'complete')

    def test_radio_channel_request_keeps_ap_off_without_stopping_radio(self):
        self.assertEqual(channel_plan(5), {'operation': 'write', 'form': 'wireless_2g',
            'wireless_2g_channel': '5', 'wireless_2g_enable': 'off', 'wireless_2g_disabled_all': 'off'})
        for value in (0, 14, '5', True, 5.0):
            with self.assertRaises(Failure):
                channel_plan(value)

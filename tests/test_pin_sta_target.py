import unittest
from tools.pin_sta_target import select_target, pin_target
from tools.read_sta_state import Failure
from tests.test_probe_sta_config import PlainProtocol


class PinTargetTests(unittest.TestCase):
    def test_two_ghz_uses_primary_band_not_colocated_ap(self):
        text = '''SSID 1 : TARGET
    BSSID 1 : 02:11:22:33:44:55
         Signal : 60%
         Band : 2.4 GHz
         Channel : 5
         Colocated AP Band : 5 GHz
         Channel : 124
'''
        self.assertEqual(select_target(text, 'TARGET', '2g'), ('02:11:22:33:44:55', 5))
        with self.assertRaises(Failure):
            select_target(text, 'TARGET', '5g')
    def test_scan_selects_exact_ssid_and_five_ghz_only(self):
        text = '''SSID 1 : TARGET
    BSSID 1 : 02:11:22:33:44:55
         Signal : 40%
         Band : 6 GHz
         Channel : 69
    BSSID 2 : 02:11:22:33:44:66
         Signal : 30%
         Band : 5 GHz
         Channel : 124
SSID 2 : OTHER
    BSSID 1 : 02:11:22:33:44:77
         Signal : 90%
         Band : 5 GHz
         Channel : 36
'''
        value = select_target(text, 'TARGET')
        self.assertEqual(value, ('02:11:22:33:44:66', 124))
        with self.assertRaises(Failure):
            select_target(text, 'MISSING')

    def test_pin_request_rejects_non_mac_and_sets_only_known_fields(self):
        class Device:
            def post(self, route, payload, token):
                self.payload = payload
                return {'success': True, 'data': {}}
        d = Device()
        with self.assertRaises(Failure):
            pin_target(d, PlainProtocol(), 'token', 'bad;command')
        pin_target(d, PlainProtocol(), 'token', '02:11:22:33:44:66')
        self.assertIn(b'locktoap_5g=on', d.payload)
        self.assertNotIn(b'psk_key', d.payload)

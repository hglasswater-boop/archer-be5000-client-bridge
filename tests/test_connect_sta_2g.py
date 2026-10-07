import unittest
from tools.connect_sta_2g import plan_2g
from tools.read_sta_state import Failure


class TwoGHzTests(unittest.TestCase):
    def test_plan_enables_only_two_ghz_with_existing_wifi_key(self):
        plan = plan_2g('TARGET', 'WiFiTestSecret')
        self.assertEqual(plan['enable_2g'], 'on')
        self.assertEqual(plan['enable_5g'], 'off')
        self.assertEqual(plan['psk_version_2g'], 'rsn')
        self.assertNotIn('psk_key_5g', plan)
        for value in ('bad;command', '', 'x' * 33):
            with self.assertRaises(Failure):
                plan_2g(value, 'WiFiTestSecret')

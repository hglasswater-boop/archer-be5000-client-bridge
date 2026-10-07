import unittest
from tools.enable_local_ssh import enable_local_ssh, ROUTE
from tests.test_probe_sta_config import PlainProtocol


class LocalSSHTests(unittest.TestCase):
    def test_exact_self_ip_permission_request_contains_no_password_change(self):
        class Device:
            def post(self, route, body, token):
                self.call = route, body
                return {'success': True, 'data': {}}
        device = Device()
        self.assertTrue(enable_local_ssh(device, PlainProtocol(), 'token'))
        self.assertEqual(device.call, (ROUTE, b'operation=app_user_agree&ssh_is_enable=1'))

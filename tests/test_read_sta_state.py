import hashlib
import hmac
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

from tools.read_sta_state import (
    Crypto, Failure, Protocol, Transport, collect, sanitize_sta, signature_text,
    split_signature, validate_password, write_report, sanitize_network,
)


class BoundaryTests(unittest.TestCase):
    def test_signature_chunk_boundaries_and_replacement_hash(self):
        self.assertEqual(split_signature('x' * 107), ['x' * 53, 'x' * 53, 'x'])
        self.assertEqual(signature_text('a' * 64, 120, 'k=1&i=2'),
                         'k=1&i=2&h=' + 'a' * 64 + '&s=120')
        self.assertEqual(signature_text('b' * 64, 130), 'h=' + 'b' * 64 + '&s=130')

    def test_password_validation(self):
        validate_password('Visible password!')
        for value in ['', 'x' * 33, 'x\n', '\u65e5', '\x7f']:
            with self.assertRaises(Failure):
                validate_password(value)

    def test_sta_report_never_copies_unknown_or_secret_values(self):
        data = {'enable_5g': 'off', 'connected_5g': False, 'ssid_5g': 'PRIVATE',
                'psk_key_5g': 'SECRET', 'surprise': {'password': 'SECRET'},
                'mode': 'router', 'status_5g': {'password': 'SECRET'}}
        result = sanitize_sta(data)
        self.assertEqual(result['values'], {'enable_5g': 'off', 'connected_5g': False,
                                           'mode': 'router'})
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_report_refuses_outside_path_and_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / 'local-evidence'
            local.mkdir()
            target = local / 'result.json'
            write_report(target, {'ok': True}, root)
            with self.assertRaises(Failure):
                write_report(target, {'ok': False}, root)
            with self.assertRaises(Failure):
                write_report(root / 'public.json', {}, root)

    def test_transport_rejects_write_and_unknown_route_before_connection(self):
        transport = Transport('192.168.0.52')
        for route, payload in [('/admin/system?form=reboot', b'operation=read'),
                               ('/admin/wireless?form=wireless_connect_to_network',
                                b'operation=write')]:
            with patch('http.client.HTTPConnection') as connection:
                with self.assertRaises(Failure):
                    transport.post(route, payload)
                connection.assert_not_called()

    def test_mode_flags_are_bounded_and_keys_are_omitted(self):
        result = sanitize_sta({'wds_mode_5g': '2', 'locktoap_5g': 'off',
                               'psk_version_5g': 'sae_transition', 'psk_key_5g': 'SECRET'})
        self.assertEqual(result['values']['wds_mode_5g'], '2')
        self.assertEqual(result['values']['psk_version_5g'], 'sae_transition')
        self.assertNotIn('SECRET', json.dumps(result))

    def test_secret_shape_uses_only_fixed_labels(self):
        result = sanitize_sta({'ssid_5g': 'PRIVATE', 'psk_key_5g': '********',
                               'ssid_2g': '', 'psk_key_2g': None})
        self.assertEqual(result['redacted_fields'], {'ssid_5g': 'present',
            'psk_key_5g': 'masked', 'ssid_2g': 'empty', 'psk_key_2g': 'invalid-type'})
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_network_report_validates_addresses_and_excludes_secrets(self):
        result = sanitize_network({'ipaddr': '192.168.0.1', 'enable': 'on',
                                   'ipaddr_start': '192.168.0.50', 'leasetime': 120,
                                   'password': 'SECRET', 'dns1': 'PRIVATE',
                                   'gateway': 'not-an-address'})
        self.assertEqual(result['values'], {'ipaddr': '192.168.0.1', 'enable': 'on',
                                           'ipaddr_start': '192.168.0.50', 'leasetime': 120})
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('PRIVATE', json.dumps(result))


class FakeCrypto:
    def call(self, operation, **kwargs):
        if operation == 'aes-encrypt':
            return 'Q0lQSEVS'
        if operation == 'rsa-v15':
            return 'a' * 512
        if operation == 'rsa-oaep':
            return 'b' * 512
        if operation == 'aes-decrypt':
            return kwargs['data']
        raise AssertionError(operation)


class FakeTransport:
    def __init__(self, login_success=True, fail_read=False):
        self.calls = []
        self.cookie = ''
        self.login_success = login_success
        self.fail_read = fail_read

    def post(self, route, payload, token=''):
        self.calls.append((route, parse_qs(payload.decode()), token))
        if route.startswith('/device_config'):
            return {'success': True, 'data': {
                'certification': ['SG CLS L1 STAGE2'], 'supportJPFeatures': True,
                'supportOperationMode': ['router', 'ap'], 'supportDwds': False}}
        if route.endswith('form=keys'):
            return {'success': True, 'data': {'password': ['f' * 512, '010001'],
                                              'username': '', 'mode': 'router'}}
        if route.endswith('form=auth'):
            return {'success': True, 'data': {'key': ['f' * 512, '010001'], 'seq': 100}}
        if route.endswith('form=login'):
            if self.login_success:
                self.cookie = 'sysauth=' + 'c' * 32
                response = {'success': True, 'data': {'stok': 'd' * 32}}
            else:
                response = {'success': False, 'errorcode': 'user conflict',
                            'data': {'addr': 'PRIVATE'}}
        elif route.endswith('form=logout'):
            response = {'success': True, 'data': {}}
        elif route.endswith('form=lan_ipv4'):
            response = {'success': True, 'data': {'ipaddr': '192.168.0.1', 'password': 'SECRET'}}
        elif route.endswith('form=setting'):
            response = {'success': True, 'data': {'enable': 'on'}}
        elif self.fail_read:
            raise Failure('network request failed')
        else:
            response = {'success': True, 'data': {'enable_5g': 'off',
                                                 'psk_key_5g': 'SECRET'}}
        return {'data': json.dumps(response)}


class LifecycleTests(unittest.TestCase):
    def test_success_reads_only_known_routes_and_logs_out(self):
        transport = FakeTransport()
        result = collect(transport, FakeCrypto(), lambda: 'ExistingPassword')
        self.assertEqual(result['outcome'], 'read-complete')
        self.assertEqual(result['logout'], 'complete')
        self.assertNotIn('SECRET', json.dumps(result))
        routes = [c[0] for c in transport.calls]
        self.assertEqual(len(routes), 7)
        self.assertTrue(routes[-1].endswith('form=logout'))
        login = transport.calls[3][1]
        self.assertEqual(set(login), {'sign', 'data'})
        self.assertNotIn('ExistingPassword', str(transport.calls))
        # Normal login plaintext is encrypted once and has no force/confirm field.
        class Recorder(FakeCrypto):
            def call(self, operation, **kwargs):
                if operation == 'aes-encrypt' and 'operation=login' in kwargs['data']:
                    self.login_plaintext = parse_qs(kwargs['data'])
                return super().call(operation, **kwargs)
        crypto = Recorder()
        collect(FakeTransport(), crypto, lambda: 'ExistingPassword')
        self.assertEqual(set(crypto.login_plaintext), {'password', 'operation'})
        self.assertEqual(crypto.login_plaintext['operation'], ['login'])

    def test_login_failure_stops_without_retry_or_logout(self):
        transport = FakeTransport(login_success=False)
        result = collect(transport, FakeCrypto(), lambda: 'ExistingPassword')
        self.assertEqual(result['outcome'], 'stopped')
        self.assertEqual(len(transport.calls), 4)
        self.assertEqual(result['reason'], 'login failed: user conflict')
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_read_failure_still_ends_own_session_once(self):
        transport = FakeTransport(fail_read=True)
        result = collect(transport, FakeCrypto(), lambda: 'ExistingPassword')
        self.assertEqual(result['outcome'], 'stopped')
        self.assertEqual(result['logout'], 'complete')
        self.assertTrue(transport.calls[-1][0].endswith('form=logout'))

    def test_wrong_protocol_stops_before_password(self):
        transport = FakeTransport()
        transport.post = lambda *args, **kwargs: {'success': True, 'data': {
            'certification': ['OTHER'], 'supportJPFeatures': True,
            'supportOperationMode': ['router', 'ap']}}
        with patch('builtins.input', side_effect=AssertionError('must not prompt')):
            result = collect(transport, FakeCrypto(), lambda: input())
        self.assertEqual(result['outcome'], 'stopped')

    def test_network_baseline_adds_only_two_read_requests(self):
        transport = FakeTransport()
        result = collect(transport, FakeCrypto(), lambda: 'ExistingPassword', network_baseline=True)
        self.assertEqual(result['outcome'], 'read-complete')
        self.assertEqual(len(transport.calls), 9)
        self.assertEqual(result['authenticated_reads']['/admin/network?form=lan_ipv4']['values'],
                         {'ipaddr': '192.168.0.1'})
        self.assertNotIn('SECRET', json.dumps(result))

    def test_common_sta_status_is_not_sent_and_failure_identifies_route(self):
        transport = FakeTransport(fail_read=True)
        result = collect(transport, FakeCrypto(), lambda: 'ExistingPassword', network_baseline=True)
        self.assertEqual(result['failed_read'], '/admin/system?form=sysmode')
        self.assertEqual(result['logout'], 'complete')
        self.assertFalse(any('wireless_connect_status' in c[0] for c in transport.calls))


class HttpTests(unittest.TestCase):
    def test_changed_management_address_is_explicit_and_source_bound(self):
        with patch('http.client.HTTPConnection') as factory:
            response = factory.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"success":true,"data":{}}'
            Transport('192.168.1.210', '192.168.1.1').post('/device_config?form=config', b'operation=read')
            factory.assert_called_once_with('192.168.1.1', 80, timeout=5,
                                            source_address=('192.168.1.210', 0))
        for source, target in [('192.168.0.52', '192.168.1.1'),
                               ('192.168.1.210', '192.168.0.1'),
                               ('192.168.1.210', '192.168.1.2'),
                               ('192.168.1.1', '192.168.1.1'),
                               ('192.168.1.210', 'example.com')]:
            with self.assertRaises(Failure):
                Transport(source, target)

    def test_source_bind_redirect_and_oversize_rejection(self):
        for status, body in [(302, b'{}'), (200, b'x' * 65537)]:
            with patch('http.client.HTTPConnection') as factory:
                response = factory.return_value.getresponse.return_value
                response.status = status
                response.read.return_value = body
                with self.assertRaises(Failure):
                    Transport('192.168.0.52').post('/device_config?form=config', b'operation=read')
                factory.assert_called_once_with('192.168.0.1', 80, timeout=5,
                                                source_address=('192.168.0.52', 0))
                response.read.assert_called_once_with(65537)
                factory.return_value.close.assert_called_once()

    def test_network_failure_never_retries_or_exposes_exception(self):
        with patch('http.client.HTTPConnection') as factory:
            factory.return_value.request.side_effect = OSError('SECRET')
            with self.assertRaisesRegex(Failure, '^network request or JSON response failed$'):
                Transport('192.168.0.52').post('/login?form=keys', b'operation=read')
            factory.assert_called_once()
            factory.return_value.request.assert_called_once()

    def test_read_without_auth_rejected_and_invalid_source_rejected(self):
        with patch('http.client.HTTPConnection') as factory:
            with self.assertRaises(Failure):
                Transport('192.168.0.52').post('/admin/system?form=sysmode', b'sign=aa&data=QQ==')
            factory.assert_not_called()
        for address in ['192.168.0.1', '192.168.0.255', '8.8.8.8', '::1', 'invalid']:
            with self.assertRaises(Failure):
                Transport(address)


@unittest.skipUnless(shutil.which('node'), 'Node.js required')
class CryptoTests(unittest.TestCase):
    def setUp(self):
        self.crypto = Crypto(shutil.which('node'))

    def test_nist_aes_cbc_block_and_pkcs7_roundtrip(self):
        key = '2b7e151628aed2a6abf7158809cf4f3c'
        iv = '000102030405060708090a0b0c0d0e0f'
        result = self.crypto.call('aes-encrypt', key=key, iv=iv,
                                 data='6bc1bee22e409f96e93d7e117393172a', inputHex=True)
        import base64
        self.assertEqual(base64.b64decode(result)[:16].hex(),
                         '7649abac8119b246cee98e9b12e9197d')
        encrypted = self.crypto.call('aes-encrypt', key=key, iv=iv, data='text')
        self.assertEqual(self.crypto.call('aes-decrypt', key=key, iv=iv,
                                          data=encrypted), 'text')

    def test_rsa_padding_is_independently_decrypted(self):
        # Generate a temporary test key. RAW private decrypt avoids Node's
        # version-dependent restrictions on v1.5 privateDecrypt.
        setup = """const c=require('node:crypto');
        const k=c.generateKeyPairSync('rsa',{modulusLength:2048});
        const j=k.publicKey.export({format:'jwk'});
        process.stdout.write(JSON.stringify({n:Buffer.from(j.n,'base64url').toString('hex'),
          e:Buffer.from(j.e,'base64url').toString('hex'),
          p:k.privateKey.export({format:'pem',type:'pkcs8'})}));"""
        fixture = json.loads(subprocess.check_output([self.crypto.node, '-e', setup]))
        for operation in ['rsa-v15', 'rsa-oaep']:
            encrypted = self.crypto.call(operation, n=fixture['n'], e=fixture['e'],
                                         data='padding-check')
            script = """const c=require('node:crypto');let s='';
            process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{
              const j=JSON.parse(s); const b=Buffer.from(j.c,'hex');
              if(j.op==='rsa-v15') {
                const p=c.privateDecrypt({key:j.p,padding:c.constants.RSA_NO_PADDING},b);
                if(p[0]!==0||p[1]!==2)throw Error('padding');
                const i=p.indexOf(0,2);if(i<10)throw Error('padding');
                process.stdout.write(p.subarray(i+1));
              } else process.stdout.write(c.privateDecrypt({key:j.p,
                padding:c.constants.RSA_PKCS1_OAEP_PADDING,oaepHash:'sha1'},b));
            });"""
            plain = subprocess.check_output([self.crypto.node, '-e', script],
                input=json.dumps({'p': fixture['p'], 'c': encrypted, 'op': operation}).encode())
            self.assertEqual(plain, b'padding-check')
            self.assertEqual(len(encrypted), 512)

    def test_authenticated_signature_matches_python_hmac(self):
        protocol = Protocol(self.crypto, ['f' * 512, '010001'], 100,
                            '0' * 64, key='1234567890123456', iv='6543210987654321')
        body = parse_qs(protocol.encrypt('operation=read').decode())
        cipher = body['data'][0]
        text = 'h=' + hashlib.sha256(cipher.encode()).hexdigest() + '&s=' + str(100 + len(cipher))
        key = b'k=1234567890123456&i=6543210987654321'
        expected = ''.join(hmac.new(key, c.encode(), hashlib.sha256).hexdigest()
                           for c in split_signature(text))
        self.assertEqual(body['sign'], [expected])

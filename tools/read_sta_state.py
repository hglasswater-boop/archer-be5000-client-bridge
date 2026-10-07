"""Bounded normal-auth getter for the observed JP BE5000 protocol, no setters."""
import argparse
import datetime
import getpass
import hashlib
import hmac
import http.client
import ipaddress
import json
import re
import secrets
import shutil
import subprocess
import sys
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlencode

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = frozenset(['/device_config?form=config', '/login?form=keys', '/login?form=auth'])
READS = frozenset(['/admin/system?form=sysmode',
                   '/admin/wireless?form=wireless_connect_to_network'])
STATUS_ROUTE = '/admin/wireless?form=wireless_connect_status'
STATUS_READS = frozenset([STATUS_ROUTE])
DIAGNOSTIC_READS = frozenset(['/admin/syslog?form=log', '/admin/syslog?form=filter',
                             '/admin/easymesh?form=easymesh_enable'])
NETWORK_READS = frozenset(['/admin/network?form=lan_ipv4', '/admin/dhcps?form=setting'])
LOGIN = '/login?form=login'
LOGOUT = '/admin/system?form=logout'
LIMIT = 65536
FEATURES = ('supportOperationMode', 'supportDwds', 'supportWdsDualmode',
            'supportNDProxy', 'supportMulticastForwarding', 'supportJPFeatures',
            'certification')
SAFE_ERRORS = frozenset(['user conflict', 'login failed', 'exceeded max attempts',
                         'multiple login', 'permission denied', 'timeout',
                         'auto upgrading', 'access', 'logining'])


class Failure(Exception):
    """Messages are fixed or allowlisted, never copied from responses/exceptions."""


def validate_password(password):
    if not isinstance(password, str) or not 1 <= len(password) <= 32 or any(
            not 32 <= ord(c) <= 126 for c in password):
        raise Failure('password must be 1-32 visible ASCII characters')


def success(payload, stage):
    if not isinstance(payload, dict) or payload.get('success') is not True:
        error = next((payload.get(k) for k in ('errorCode', 'errorcode', 'error_code', 'error')
                      if isinstance(payload, dict) and payload.get(k)), None)
        error = error if isinstance(error, str) and error in SAFE_ERRORS else 'unrecognized response'
        raise Failure(stage + ' failed: ' + error)
    return payload.get('data')


def public_key(key):
    if not isinstance(key, list) or len(key) != 2 or not all(isinstance(x, str) for x in key):
        raise Failure('unexpected RSA public key')
    n, e = key
    if not re.fullmatch(r'[0-9a-fA-F]{512}', n) or not re.fullmatch(r'[0-9a-fA-F]{1,8}', e):
        raise Failure('unexpected RSA public key')
    if int(n, 16).bit_length() != 2048 or int(n, 16) % 2 != 1 or int(e, 16) != 65537:
        raise Failure('unexpected RSA public key')
    return key


class Crypto:
    def __init__(self, node):
        self.node = node

    def call(self, operation, **kwargs):
        try:
            result = subprocess.run([self.node, str(ROOT / 'tools' / 'sta_crypto.cjs')],
                input=json.dumps({'operation': operation, **kwargs}).encode(),
                capture_output=True, timeout=5, check=False)
            if result.returncode != 0 or len(result.stdout) > 256 * 1024:
                raise Failure('crypto operation failed')
            output = json.loads(result.stdout)['result']
            if not isinstance(output, str):
                raise Failure('crypto operation failed')
            return output
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            raise Failure('crypto operation failed') from None


def split_signature(text):
    return [text[i:i + 53] for i in range(0, len(text), 53)]


def signature_text(digest, sequence, formatted_key=None):
    text = f'h={digest}&s={sequence}'
    return f'{formatted_key}&{text}' if formatted_key else text


class Protocol:
    def __init__(self, crypto, rsa, sequence, digest, *, key=None, iv=None):
        self.crypto, self.rsa = crypto, public_key(rsa)
        if type(sequence) is not int or not 0 < sequence < 2 ** 53:
            raise Failure('unexpected sequence')
        self.sequence, self.digest = sequence, digest
        self.key = key or ''.join(str(secrets.randbelow(10)) for _ in range(16))
        self.iv = iv or ''.join(str(secrets.randbelow(10)) for _ in range(16))
        if not re.fullmatch(r'[0-9]{16}', self.key) or not re.fullmatch(r'[0-9]{16}', self.iv):
            raise Failure('unexpected AES key format')
        self.formatted = f'k={self.key}&i={self.iv}'

    def encrypt(self, plaintext, *, login=False):
        cipher = self.crypto.call('aes-encrypt', key=self.key.encode().hex(),
                                  iv=self.iv.encode().hex(), data=plaintext)
        digest = self.digest if login else hashlib.sha256(cipher.encode('ascii')).hexdigest()
        text = signature_text(digest, self.sequence + len(cipher), self.formatted if login else None)
        if login:
            sign = ''.join(self.crypto.call('rsa-oaep', n=self.rsa[0], e=self.rsa[1], data=c)
                           for c in split_signature(text))
        else:
            sign = ''.join(hmac.new(self.formatted.encode(), c.encode(), hashlib.sha256).hexdigest()
                           for c in split_signature(text))
        return urlencode({'sign': sign, 'data': cipher}).encode('ascii')

    def decrypt(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), str) or not payload['data']:
            raise Failure('encrypted response missing')
        try:
            plain = self.crypto.call('aes-decrypt', key=self.key.encode().hex(),
                                     iv=self.iv.encode().hex(), data=payload['data'])
            result = json.loads(plain)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except ValueError:
            raise Failure('encrypted response invalid') from None


class Transport:
    def __init__(self, source_ip, target_ip='192.168.0.1'):
        try:
            if target_ip not in ('192.168.0.1', '192.168.1.1'):
                raise ValueError()
            address = ipaddress.IPv4Address(source_ip)
            network = ipaddress.IPv4Network(target_ip + '/24', strict=False)
            if address not in network or int(address) & 255 in (0, 1, 255):
                raise ValueError()
        except ValueError:
            raise Failure('target must be an approved management IP; source must be a PC address in its /24') from None
        self.source_ip, self.target_ip, self.cookie = str(address), target_ip, ''

    def post(self, route, payload, token=''):
        if route not in PUBLIC | READS | STATUS_READS | NETWORK_READS | DIAGNOSTIC_READS | {LOGIN, LOGOUT}:
            raise Failure('request route is not allowlisted')
        if not isinstance(payload, bytes) or len(payload) > 16384:
            raise Failure('request payload invalid')
        try:
            fields = parse_qs(payload.decode('ascii'), strict_parsing=True)
        except ValueError:
            raise Failure('request payload invalid') from None
        if route in PUBLIC:
            if fields != {'operation': ['read']} or token:
                raise Failure('public request must be read-only')
        else:
            if set(fields) != {'sign', 'data'} or any(len(v) != 1 for v in fields.values()):
                raise Failure('encrypted request required')
            if not re.fullmatch(r'[0-9a-f]+', fields['sign'][0]) or not re.fullmatch(
                    r'[A-Za-z0-9+/]+={0,2}', fields['data'][0]):
                raise Failure('encrypted request invalid')
            if route == LOGIN and token:
                raise Failure('login must not reuse a token')
            if route != LOGIN and (not re.fullmatch(r'[0-9a-f]{16,128}', token) or not self.cookie):
                raise Failure('authenticated session required')
        connection = http.client.HTTPConnection(self.target_ip, 80, timeout=5,
                                                source_address=(self.source_ip, 0))
        try:
            headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Cache-Control': 'no-cache'}
            if token:
                headers['Cookie'] = self.cookie
            connection.request('POST', '/cgi-bin/luci/;stok=' + token + route,
                               body=payload, headers=headers)
            response = connection.getresponse()
            data = response.read(LIMIT + 1)
            if response.status != 200 or len(data) > LIMIT:
                raise Failure('HTTP response rejected')
            if route == LOGIN:
                for name, value in response.getheaders():
                    if name.lower() == 'set-cookie':
                        cookies = SimpleCookie()
                        cookies.load(value)
                        if 'sysauth' in cookies:
                            cookie = cookies['sysauth'].value
                            if re.fullmatch(r'[0-9a-f]{16,128}', cookie):
                                self.cookie = 'sysauth=' + cookie
            result = json.loads(data)
            if not isinstance(result, dict):
                raise Failure('HTTP response invalid')
            return result
        except (OSError, http.client.HTTPException, ValueError):
            raise Failure('network request or JSON response failed') from None
        finally:
            connection.close()


def sanitize_sta(data):
    if not isinstance(data, dict) or len(data) > 512:
        raise Failure('state response must be an object')
    # Explicit allowlist. Unknown/nested fields are never copied into evidence.
    safe_names = {'mode', 'support', 'enable_2g', 'enable_5g', 'enable',
                  'connected_2g', 'connected_5g', 'status_2g', 'status_5g',
                  'wds_status', 'encryption_2g', 'encryption_5g', 'connect_status',
                  'wds_mode_2g', 'wds_mode_5g', 'locktoap_2g', 'locktoap_5g',
                  'psk_version_2g', 'psk_version_5g', 'psk_cipher_2g', 'psk_cipher_5g'}
    safe_values = {'router', 'ap', 'client', 'repeater', 'hotspot', 'yes', 'no',
                   'on', 'off', 'connected', 'disconnected', 'disabled', 'enabled',
                   'psk', 'psk_sae', 'none', 'wpa2', 'wpa3', 'AES', 'RSN', 'rsn',
                   'sae_transition', 'sae_only', 'aes', 'auto', 'wpa', 'tkip',
                   'connecting', '0', '1', '2'}
    fields = sorted(k for k in data if isinstance(k, str) and re.fullmatch(r'[A-Za-z0-9_]{1,80}', k))
    values = {k: v for k, v in data.items() if k in safe_names and (
        type(v) is bool or type(v) is int and -1 <= v <= 10 or
        isinstance(v, str) and v in safe_values)}
    secret_fields = {}
    for key in ('ssid_2g', 'ssid_5g', 'psk_key_2g', 'psk_key_5g'):
        if key in data:
            value = data[key]
            secret_fields[key] = ('invalid-type' if not isinstance(value, str) else
                                  'empty' if value == '' else
                                  'masked' if re.fullmatch(r'\*+', value) else 'present')
    return {'fields': fields, 'values': values, 'redacted_fields': secret_fields}


def sanitize_network(data):
    result = sanitize_sta(data)
    for key, value in data.items():
        if key in ('ipaddr', 'ipaddr_start', 'ipaddr_end', 'netmask', 'gateway', 'start', 'end'):
            try:
                result['values'][key] = str(ipaddress.IPv4Address(value)) if isinstance(value, str) else ''
            except ValueError:
                continue
            if not result['values'][key]:
                del result['values'][key]
        elif key in ('leasetime', 'lease_time') and type(value) is int and 1 <= value <= 10080:
            result['values'][key] = value
    return result


def login_session(transport, crypto, password_provider):
    """Normal local login only. Caller owns logout; never forces other sessions out."""
    keys = success(transport.post('/login?form=keys', b'operation=read'), 'keys')
    if not isinstance(keys, dict) or keys.get('mode') != 'router' or keys.get('username') != '':
        raise Failure('unexpected login mode')
    credentials = public_key(keys.get('password'))
    password = password_provider()
    validate_password(password)
    challenge = success(transport.post('/login?form=auth', b'operation=read'), 'challenge')
    if not isinstance(challenge, dict):
        raise Failure('unexpected challenge')
    protocol = Protocol(crypto, challenge.get('key'), challenge.get('seq'),
                        hashlib.sha256(('admin' + password).encode()).hexdigest())
    encrypted_password = crypto.call('rsa-v15', n=credentials[0], e=credentials[1], data=password)
    del password
    body = protocol.encrypt(urlencode({'password': encrypted_password, 'operation': 'login'}), login=True)
    login_data = success(protocol.decrypt(transport.post(LOGIN, body)), 'login')
    if not isinstance(login_data, dict) or not isinstance(login_data.get('stok'), str) or not re.fullmatch(
            r'[0-9a-f]{16,128}', login_data['stok']):
        raise Failure('login token missing')
    if not transport.cookie:
        raise Failure('login cookie missing')
    return protocol, login_data['stok']


def collect(transport, crypto, password_provider, *, preflight_only=False, network_baseline=False):
    report = {'outcome': 'stopped', 'logout': 'not-needed', 'authenticated_reads': {}}
    protocol, token = None, ''
    try:
        config = success(transport.post('/device_config?form=config', b'operation=read'), 'preflight')
        if not isinstance(config, dict) or config.get('certification') != ['SG CLS L1 STAGE2'] or (
                config.get('supportJPFeatures') is not True or
                config.get('supportOperationMode') != ['router', 'ap']):
            raise Failure('device feature/protocol mismatch')
        report['features'] = {k: config[k] for k in FEATURES if k in config and (
            type(config[k]) is bool or k in ('certification', 'supportOperationMode'))}
        if preflight_only:
            report['outcome'] = 'preflight-complete'
            return report
        protocol, token = login_session(transport, crypto, password_provider)
        for route in sorted(READS | NETWORK_READS if network_baseline else READS):
            report['failed_read'] = route
            data = success(protocol.decrypt(transport.post(route, protocol.encrypt('operation=read'), token)), 'read')
            cleaner = sanitize_network if route.startswith(('/admin/network?', '/admin/dhcps?')) else sanitize_sta
            report['authenticated_reads'][route] = cleaner(data)
            del report['failed_read']
        report['outcome'] = 'read-complete'
    except Failure as error:
        report['reason'] = str(error)
    finally:
        if protocol and token and transport.cookie:
            try:
                success(protocol.decrypt(transport.post(LOGOUT, protocol.encrypt(''), token)), 'logout')
                report['logout'] = 'complete'
            except Failure:
                report['logout'] = 'failed'
        transport.cookie = ''
    return report


def write_report(path, report, root=ROOT):
    directory = root / 'local-evidence'
    if directory.is_symlink() or directory.resolve().parent != root.resolve():
        raise Failure('local-evidence must be a directory inside the repository')
    directory = directory.resolve()
    if path.resolve().parent != directory or path.is_symlink():
        raise Failure('report must be a new file directly under local-evidence')
    directory.mkdir(exist_ok=True)
    try:
        with path.open('x', encoding='utf8') as output:
            json.dump(report, output, indent=2, ensure_ascii=True)
            output.write('\n')
    except FileExistsError:
        raise Failure('report already exists; no overwrite performed') from None


def prompt_password():
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise Failure('run in an interactive local terminal for password input')
    return getpass.getpass('Existing BE5000 admin password (hidden): ')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-ip', required=True, help='PC Ethernet IPv4 in the target management subnet')
    parser.add_argument('--target-ip', choices=('192.168.0.1', '192.168.1.1'), default='192.168.0.1',
                        help='explicit BE5000 management IP; verify device MAC first')
    parser.add_argument('--node', default=shutil.which('node'), help='Node.js executable')
    parser.add_argument('--preflight-only', action='store_true', help='public feature read only, no login')
    parser.add_argument('--network-baseline', action='store_true', help='also read LAN/DHCP/STA status baseline')
    args = parser.parse_args(argv)
    try:
        if not args.preflight_only and not args.node:
            raise Failure('Node.js executable required')
        if not args.preflight_only and (not sys.stdin.isatty() or not sys.stderr.isatty()):
            raise Failure('run in an interactive local terminal for password input')
        transport = Transport(args.source_ip, args.target_ip)
        report = collect(transport, Crypto(args.node), prompt_password,
                         preflight_only=args.preflight_only, network_baseline=args.network_baseline)
        stamp = datetime.datetime.now(datetime.timezone.utc)
        report.update(captured_at=stamp.isoformat(), target=transport.target_ip, source_ip=transport.source_ip,
                      firmware_assumption='JP/1.0 1.2.0 Build 20260420 rel.13798(4A50)')
        target = ROOT / 'local-evidence' / ('sta-read-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
        write_report(target, report)
        print('Outcome: ' + report['outcome'])
        if 'reason' in report:
            print('Reason: ' + report['reason'])
        print('Report: ' + str(target))
        return 0 if report['outcome'] in ('read-complete', 'preflight-complete') else 1
    except Failure as error:
        print('Stopped: ' + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Stopped: interrupted', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

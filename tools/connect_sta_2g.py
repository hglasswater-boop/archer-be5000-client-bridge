"""Retained 2.4GHz STA comparison using the existing configured Wi-Fi key."""
import datetime
import getpass
import re
import shutil
import sys
import time
from urllib.parse import urlencode
from .probe_sta_config import STA, request
from .read_sta_state import Crypto, Failure, LOGOUT, ROOT, Transport, login_session, prompt_password, success, write_report
from .sta_ipv4_probe import DhcpObserver


def plan_2g(ssid, key):
    if not isinstance(ssid, str) or not re.fullmatch(r'[A-Za-z0-9_.@+ -]{1,32}', ssid):
        raise Failure('target SSID outside limited format')
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_.@+-]{8,63}', key):
        raise Failure('saved Wi-Fi key cannot be used by this limited comparison')
    return {'enable_5g': 'off', 'enable_2g': 'on', 'ssid_2g': ssid,
            'encryption_2g': 'psk', 'psk_version_2g': 'rsn', 'psk_cipher_2g': 'aes', 'psk_key_2g': key}


def main():
    node = shutil.which('node')
    if not node or not sys.stdin.isatty() or not sys.stderr.isatty():
        print('Stopped: Node.js and interactive terminal are required', file=sys.stderr)
        return 1
    transport = Transport('192.168.1.52', '192.168.1.1')
    report = {'outcome': 'stopped', 'logout': 'not-needed', 'association': 'not-measured'}
    protocol, token = None, ''
    try:
        protocol, token = login_session(transport, Crypto(node), prompt_password)
        read = lambda route: request(transport, protocol, token, route)
        if read('/admin/network?form=lan_ipv4').get('ipaddr') != '192.168.1.1' or (
                read('/admin/dhcps?form=setting').get('enable') != 'off'):
            raise Failure('converter management precondition mismatch')
        state = read(STA)
        if state.get('enable_5g') != 'on' or state.get('enable_2g') != 'off':
            raise Failure('expected retained 5GHz baseline')
        plan = plan_2g(getpass.getpass('Target 2.4GHz SSID (hidden): '), state.get('psk_key_5g'))
        report['write_attempted'] = True
        success(protocol.decrypt(transport.post(STA,
            protocol.encrypt(urlencode({'operation': 'write', **plan})), token)), 'sta-2g-write')
        print('2.4GHz STA saved; waiting for radio update')
        time.sleep(20)
        current = read(STA)
        report['configuration_verified'] = all(current.get(k) == v for k, v in plan.items())
        report['sta_2g_enabled'] = current.get('enable_2g') == 'on'
        report['sta_5g_disabled'] = current.get('enable_5g') == 'off'
        if not report['configuration_verified']:
            raise Failure('2.4GHz STA readback mismatch')
        report['ipv4'] = DhcpObserver().before()
        report['outcome'] = 'sta-2g-retained'
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
    stamp = datetime.datetime.now(datetime.timezone.utc)
    report['captured_at'] = stamp.isoformat()
    path = ROOT / 'local-evidence' / ('sta-2g-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    write_report(path, report)
    print('Outcome: ' + report['outcome'])
    print('Report: ' + str(path))
    return 0 if report['outcome'] == 'sta-2g-retained' else 1


if __name__ == '__main__':
    raise SystemExit(main())

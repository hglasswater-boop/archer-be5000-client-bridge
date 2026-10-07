"""Apply a locally entered Wi-Fi key to the retained 2.4GHz WPA2 target."""
import datetime
import argparse
import getpass
import shutil
import sys
import time
from urllib.parse import urlencode

from .connect_sta_2g import plan_2g
from .probe_sta_config import STA, request
from .read_sta_diagnostics import observe_authenticated
from .read_sta_state import Crypto, Failure, LOGOUT, ROOT, Transport, login_session, prompt_password, success, write_report
from .sta_ipv4_probe import DhcpObserver
from .pin_sta_target import refresh_wifi_scan, select_target
import subprocess


def channel_plan(channel):
    if type(channel) is not int or not 1 <= channel <= 13:
        raise Failure('target channel outside limited 2.4GHz comparison')
    return {'operation': 'write', 'form': 'wireless_2g', 'wireless_2g_channel': str(channel),
            'wireless_2g_enable': 'off', 'wireless_2g_disabled_all': 'off'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--align-scan-channel', action='store_true', help='reuse saved key and align radio to the scanned target channel')
    args = parser.parse_args()
    node = shutil.which('node')
    if not node or not sys.stdin.isatty() or not sys.stderr.isatty():
        print('Stopped: Node.js and interactive terminal are required', file=sys.stderr)
        return 1
    report = {'outcome': 'stopped', 'logout': 'not-needed', 'association': 'not-measured'}
    transport = Transport('192.168.1.52', '192.168.1.1')
    protocol, token = None, ''
    try:
        protocol, token = login_session(transport, Crypto(node), prompt_password)
        read = lambda route: request(transport, protocol, token, route)
        if read('/admin/network?form=lan_ipv4').get('ipaddr') != '192.168.1.1' or read('/admin/dhcps?form=setting').get('enable') != 'off':
            raise Failure('converter management precondition mismatch')
        state = read(STA)
        if state.get('enable_2g') != 'on' or state.get('enable_5g') != 'off' or state.get('ssid_2g') != 'nisin2.4':
            raise Failure('expected retained requested 2.4GHz target')
        if args.align_scan_channel:
            plan = plan_2g(state['ssid_2g'], state.get('psk_key_2g'))
            if any(state.get(k) != v for k, v in plan.items()) or read('/admin/easymesh?form=easymesh_enable').get('enable') != 'off':
                raise Failure('retained WPA2 or Mesh-off precondition mismatch')
            for band in ('2g', '5g'):
                form = 'wireless_' + band
                radio = request(transport, protocol, token, '/admin/wireless?form=' + form, fields={'form': form})
                if radio.get(form + '_enable') != 'off' or radio.get(form + '_disabled_all') != 'off':
                    raise Failure('AP-off or radio-preservation precondition mismatch')
            refresh_wifi_scan()
            scan = subprocess.run(['netsh', 'wlan', 'show', 'networks', 'mode=bssid'], capture_output=True, timeout=10, check=False)
            if scan.returncode or len(scan.stdout) > 1048576:
                raise Failure('PC scan failed')
            _, channel = select_target(scan.stdout.decode('utf8', errors='replace'), state['ssid_2g'], '2g')
            fields = channel_plan(channel)
            report['target_channel'] = channel
            report['channel_write_attempted'] = True
            success(protocol.decrypt(transport.post('/admin/wireless?form=wireless_2g',
                protocol.encrypt(urlencode(fields)), token)), 'channel-align')
            time.sleep(10)
            radio = request(transport, protocol, token, '/admin/wireless?form=wireless_2g', fields={'form': 'wireless_2g'})
            report['channel_verified'] = str(radio.get('wireless_2g_channel')) == str(channel)
            if not report['channel_verified'] or radio.get('wireless_2g_enable') != 'off' or radio.get('wireless_2g_disabled_all') != 'off':
                raise Failure('channel or AP/radio readback mismatch')
        else:
            plan = plan_2g(state['ssid_2g'], getpass.getpass('Target Wi-Fi password (hidden): '))
            report['key_already_matched'] = state.get('psk_key_2g') == plan['psk_key_2g']
        report['write_attempted'] = True
        success(protocol.decrypt(transport.post(STA,
            protocol.encrypt(urlencode({'operation': 'write', **plan})), token)), 'sta-2g-write')
        print('2.4GHz target configuration saved; waiting for STA update')
        time.sleep(20)
        current = read(STA)
        report['configuration_verified'] = all(current.get(k) == v for k, v in plan.items())
        if not report['configuration_verified']:
            raise Failure('2.4GHz STA readback mismatch')
        report['ipv4'] = DhcpObserver().before()
        report['outcome'] = 'sta-2g-channel-verified' if args.align_scan_channel else 'sta-2g-key-verified'
    except Failure as error:
        report['reason'] = str(error)
    except (OSError, subprocess.SubprocessError):
        report['reason'] = 'PC scan operation failed'
    finally:
        if protocol and token and transport.cookie:
            report['diagnostics'] = {}
            try:
                observe_authenticated(transport, protocol, token, probe_mesh=True,
                    probe_radio=True, report=report['diagnostics'])
                report['diagnostics_outcome'] = 'diagnostics-complete'
            except Failure as error:
                report['diagnostics_reason'] = str(error)
            try:
                success(protocol.decrypt(transport.post(LOGOUT, protocol.encrypt(''), token)), 'logout')
                report['logout'] = 'complete'
            except Failure:
                report['logout'] = 'failed'
        transport.cookie = ''
    stamp = datetime.datetime.now(datetime.timezone.utc)
    report['captured_at'] = stamp.isoformat()
    path = ROOT / 'local-evidence' / ('sta-2g-key-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    write_report(path, report)
    print('Outcome: ' + report['outcome'])
    print('Report: ' + str(path))
    return 0 if report['outcome'] in ('sta-2g-key-verified', 'sta-2g-channel-verified') else 1


if __name__ == '__main__':
    raise SystemExit(main())

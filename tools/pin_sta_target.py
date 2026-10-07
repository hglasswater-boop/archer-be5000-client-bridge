"""Pin retained STA to an exact saved-SSID 5GHz AP from Windows scan."""
import argparse
import datetime
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlencode
from .probe_sta_config import STA, original_state, request
from .read_sta_state import Crypto, Failure, LOGOUT, ROOT, Transport, login_session, prompt_password, success, write_report
from .sta_ipv4_probe import DhcpObserver

MAC = r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}'


def select_target(text, target):
    candidates = []
    for block in re.split(r'(?m)^SSID \d+\s*:', text)[1:]:
        if block.splitlines()[0].strip() != target:
            continue
        for row in re.split(r'(?m)^\s+BSSID \d+\s*:', block)[1:]:
            mac = row.splitlines()[0].strip().lower()
            if not re.fullmatch(MAC, mac) or int(mac[:2], 16) & 1 or not int(mac.replace(':', ''), 16):
                continue
            if not re.search(r'Band\s*:\s*5 GHz', row):
                continue
            channel = re.search(r'Channel\s*:\s*([0-9]{1,3})', row)
            signal = re.search(r'Signal\s*:\s*([0-9]{1,3})%', row)
            if channel and 32 <= int(channel[1]) <= 177:
                candidates.append((int(signal[1]) if signal else 0, mac, int(channel[1])))
    if not candidates:
        raise Failure('saved target has no validated 5GHz BSSID in PC scan')
    _, mac, channel = max(candidates)
    return mac, channel


def pin_target(transport, protocol, token, mac):
    if not isinstance(mac, str) or not re.fullmatch(MAC, mac) or int(mac[:2], 16) & 1 or not int(mac.replace(':', ''), 16):
        raise Failure('target BSSID format invalid')
    fields = {'operation': 'write', 'enable_5g': 'on', 'bssid_5g': mac, 'locktoap_5g': 'on'}
    return success(protocol.decrypt(transport.post(STA, protocol.encrypt(urlencode(fields)), token)), 'pin-target')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pin-scan-target', action='store_true', required=True)
    p.parse_args()
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
        saved = original_state(state, allow_active=True)
        scan = subprocess.run(['netsh', 'wlan', 'show', 'networks', 'mode=bssid'],
                              capture_output=True, timeout=10, check=False)
        if scan.returncode or len(scan.stdout) > 1048576:
            raise Failure('PC scan failed')
        mac, channel = select_target(scan.stdout.decode('utf-8', errors='replace'), saved['ssid_5g'])
        report['target_channel'] = channel
        report['pin_write_attempted'] = True
        pin_target(transport, protocol, token, mac)
        report['pin_write_accepted'] = True
        print('BSSID pin accepted; waiting for STA update')
        time.sleep(20)
        current = read(STA)
        report['sta_kept_enabled'] = current.get('enable_5g') == 'on'
        report['pin_verified'] = current.get('locktoap_5g') == 'on' and (
            str(current.get('bssid_5g', '')).replace('-', ':').lower() == mac)
        report['saved_fields_unchanged'] = all(current.get(k) == v for k, v in saved.items())
        if not all(report[k] for k in ('sta_kept_enabled', 'pin_verified', 'saved_fields_unchanged')):
            raise Failure('pinned STA readback mismatch')
        report['ipv4'] = DhcpObserver().before()
        report['outcome'] = 'sta-target-pinned'
    except Failure as error:
        report['reason'] = str(error)
    except (OSError, subprocess.SubprocessError):
        report['reason'] = 'PC scan operation failed'
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
    path = ROOT / 'local-evidence' / ('sta-pin-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    write_report(path, report)
    print('Outcome: ' + report['outcome'])
    print('Report: ' + str(path))
    return 0 if report['outcome'] == 'sta-target-pinned' else 1


if __name__ == '__main__':
    raise SystemExit(main())

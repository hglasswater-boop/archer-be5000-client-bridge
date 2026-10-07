"""Pin retained STA to a saved-SSID AP in the selected band from Windows scan."""
import argparse
import datetime
import re
import shutil
import subprocess
import sys
import time
import ctypes
import uuid
from urllib.parse import urlencode
from .probe_sta_config import STA, original_state, request
from .read_sta_state import Crypto, Failure, LOGOUT, ROOT, Transport, login_session, prompt_password, success, write_report
from .sta_ipv4_probe import DhcpObserver
from .connect_sta_2g import plan_2g

MAC = r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}'


def select_target(text, target, band='5g'):
    if band not in ('2g', '5g'):
        raise Failure('target band outside retained STA comparison')
    candidates = []
    for block in re.split(r'(?m)^SSID \d+\s*:', text)[1:]:
        if block.splitlines()[0].strip() != target:
            continue
        for row in re.split(r'(?m)^\s+BSSID \d+\s*:', block)[1:]:
            mac = row.splitlines()[0].strip().lower()
            if not re.fullmatch(MAC, mac) or int(mac[:2], 16) & 1 or not int(mac.replace(':', ''), 16):
                continue
            primary_band = re.search(r'(?m)^\s+Band\s*:\s*(2\.4|5|6) GHz', row)
            if not primary_band or primary_band[1] != ('5' if band == '5g' else '2.4'):
                continue
            channel = re.search(r'Channel\s*:\s*([0-9]{1,3})', row)
            signal = re.search(r'Signal\s*:\s*([0-9]{1,3})%', row)
            if channel and (32 <= int(channel[1]) <= 177 if band == '5g' else 1 <= int(channel[1]) <= 14):
                candidates.append((int(signal[1]) if signal else 0, mac, int(channel[1])))
    if not candidates:
        raise Failure('saved target has no validated band BSSID in PC scan')
    _, mac, channel = max(candidates)
    return mac, channel


def pin_target(transport, protocol, token, mac, band='5g', saved=None):
    if band not in ('2g', '5g'):
        raise Failure('target band outside retained STA comparison')
    if not isinstance(mac, str) or not re.fullmatch(MAC, mac) or int(mac[:2], 16) & 1 or not int(mac.replace(':', ''), 16):
        raise Failure('target BSSID format invalid')
    fields = {'operation': 'write', 'enable_' + band: 'on', 'bssid_' + band: mac, 'locktoap_' + band: 'on'}
    if saved is not None:
        if band != '2g' or saved != plan_2g(saved.get('ssid_2g'), saved.get('psk_key_2g')):
            raise Failure('saved profile outside retained 2.4GHz baseline')
        fields.update(saved)
    return success(protocol.decrypt(transport.post(STA, protocol.encrypt(urlencode(fields)), token)), 'pin-target')


def refresh_wifi_scan():
    result = subprocess.run(['powershell', '-NoProfile', '-Command',
        '(Get-NetAdapter | Where-Object ifIndex -eq 14).InterfaceGuid'], capture_output=True, timeout=10)
    if result.returncode:
        raise Failure('Wi-Fi adapter lookup failed')
    try:
        guid = ctypes.create_string_buffer(uuid.UUID(result.stdout.decode().strip().strip('{}')).bytes_le)
    except ValueError:
        raise Failure('Wi-Fi adapter identity unavailable') from None
    w = ctypes.WinDLL('wlanapi.dll')
    handle, version = ctypes.c_void_p(), ctypes.c_uint32()
    w.WlanOpenHandle.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_void_p)]
    w.WlanScan.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    w.WlanCloseHandle.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    if w.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle)):
        raise Failure('Windows scan handle unavailable')
    try:
        if w.WlanScan(handle, guid, None, None, None):
            raise Failure('Windows active scan request rejected')
        time.sleep(5)
    finally:
        w.WlanCloseHandle(handle, None)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pin-scan-target', action='store_true', required=True)
    p.add_argument('--band', choices=('2g', '5g'), default='5g')
    p.add_argument('--diagnose-after', action='store_true', help='read both radios, Mesh and link in the same authenticated session')
    p.add_argument('--include-saved-profile', action='store_true', help='include the verified saved 2.4GHz WPA2 fields in the pin request')
    args = p.parse_args()
    if args.include_saved_profile and args.band != '2g':
        p.error('--include-saved-profile requires --band 2g')
    node = shutil.which('node')
    if not node or not sys.stdin.isatty() or not sys.stderr.isatty():
        print('Stopped: Node.js and interactive terminal are required', file=sys.stderr)
        return 1
    transport = Transport('192.168.1.52', '192.168.1.1')
    report = {'outcome': 'stopped', 'logout': 'not-needed', 'association': 'not-measured', 'band': args.band}
    protocol, token = None, ''
    try:
        protocol, token = login_session(transport, Crypto(node), prompt_password)
        read = lambda route: request(transport, protocol, token, route)
        if read('/admin/network?form=lan_ipv4').get('ipaddr') != '192.168.1.1' or (
                read('/admin/dhcps?form=setting').get('enable') != 'off'):
            raise Failure('converter management precondition mismatch')
        state = read(STA)
        if args.band == '5g':
            saved = original_state(state, allow_active=True)
        else:
            saved = plan_2g(state.get('ssid_2g'), state.get('psk_key_2g'))
            if not all(state.get(k) == v for k, v in saved.items()):
                raise Failure('expected retained WPA2 2.4GHz baseline')
        refresh_wifi_scan()
        scan = subprocess.run(['netsh', 'wlan', 'show', 'networks', 'mode=bssid'],
                              capture_output=True, timeout=10, check=False)
        if scan.returncode or len(scan.stdout) > 1048576:
            raise Failure('PC scan failed')
        mac, channel = select_target(scan.stdout.decode('utf-8', errors='replace'), saved['ssid_' + args.band], args.band)
        report['target_channel'] = channel
        report['pin_write_attempted'] = True
        pin_target(transport, protocol, token, mac, args.band,
                   saved if args.include_saved_profile else None)
        report['pin_write_accepted'] = True
        print('BSSID pin accepted; waiting for STA update')
        time.sleep(20)
        current = read(STA)
        report['sta_kept_enabled'] = current.get('enable_' + args.band) == 'on'
        report['pin_verified'] = current.get('locktoap_' + args.band) == 'on' and (
            str(current.get('bssid_' + args.band, '')).replace('-', ':').lower() == mac)
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
            if args.diagnose_after:
                from .read_sta_diagnostics import observe_authenticated
                report['diagnostics'] = {}
                try:
                    observe_authenticated(transport, protocol, token, probe_mesh=True,
                        probe_radio=True, report=report['diagnostics'])
                    report['diagnostics_outcome'] = 'diagnostics-complete'
                except Failure as error:
                    report['diagnostics_outcome'] = 'stopped'
                    report['diagnostics_reason'] = str(error)
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

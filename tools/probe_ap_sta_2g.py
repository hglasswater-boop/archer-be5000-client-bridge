"""Compare retained STA with the 2.4GHz AP temporarily enabled, then turn AP off."""
import argparse
import datetime
import shutil
import sys
import time
import subprocess
from urllib.parse import urlencode

from .connect_sta_2g import plan_2g
from .probe_sta_config import STA, request
from .read_sta_diagnostics import MESH, observe_authenticated
from .read_sta_state import Crypto, Failure, LOGOUT, ROOT, Transport, login_session, prompt_password, success, write_report
from .sta_ipv4_probe import DhcpObserver
from .pin_sta_target import refresh_wifi_scan, select_target

RADIO = '/admin/wireless?form=wireless_2g'


def scan_visibility(ap_ssid):
    refresh_wifi_scan()
    scan = subprocess.run(['netsh', 'wlan', 'show', 'networks', 'mode=bssid'], capture_output=True, timeout=10, check=False)
    if scan.returncode or len(scan.stdout) > 1048576:
        raise Failure('PC scan failed')
    text = scan.stdout.decode('utf8', errors='replace')
    result = {}
    for label, ssid in (('saved_ap_ssid', ap_ssid), ('parent', 'nisin2.4')):
        if not isinstance(ssid, str) or not ssid:
            result[label + '_visible'] = 'unavailable'
            continue
        try:
            _, channel = select_target(text, ssid, '2g')
            result[label + '_visible'] = True
            result[label + '_channel'] = channel
        except Failure:
            result[label + '_visible'] = False
    return result


def set_ap(transport, protocol, token, enabled):
    if type(enabled) is not bool:
        raise Failure('AP enable must be boolean')
    fields = {'operation': 'write', 'form': 'wireless_2g',
              'wireless_2g_enable': 'on' if enabled else 'off',
              'wireless_2g_disabled_all': 'off'}
    return success(protocol.decrypt(transport.post(RADIO, protocol.encrypt(urlencode(fields)), token)), 'ap-switch')


def probe(transport, crypto, provider, *, sleep=time.sleep, observer=None, stage=lambda s: None, target_channel=5, scan_observer=None, restart_sta=False, probe_mesh_start=False):
    report = {'outcome': 'stopped', 'logout': 'not-needed', 'ap_off': 'not-needed',
              'association': 'not-measured'}
    protocol, token, saved = None, '', None
    ap_attempted = False
    sta_restart_attempted = False
    mesh_attempted = False
    try:
        if type(target_channel) is not int or not 1 <= target_channel <= 13:
            raise Failure('target channel outside limited comparison')
        report['target_channel'] = target_channel
        protocol, token = login_session(transport, crypto, provider)
        read = lambda route: request(transport, protocol, token, route)
        if read('/admin/network?form=lan_ipv4').get('ipaddr') != '192.168.1.1' or read('/admin/dhcps?form=setting').get('enable') != 'off':
            raise Failure('converter management precondition mismatch')
        state = read(STA)
        saved = plan_2g(state.get('ssid_2g'), state.get('psk_key_2g'))
        if state.get('ssid_2g') != 'nisin2.4' or any(state.get(k) != v for k, v in saved.items()) or read(MESH).get('enable') != 'off':
            raise Failure('retained 2.4GHz target or Mesh-off mismatch')
        for band in ('2g', '5g'):
            form = 'wireless_' + band
            radio = request(transport, protocol, token, '/admin/wireless?form=' + form, fields={'form': form})
            if radio.get(form + '_enable') != 'off' or radio.get(form + '_disabled_all') != 'off':
                raise Failure('AP-off or radio-preservation precondition mismatch')
            if band == '2g' and str(radio.get('wireless_2g_channel')) != str(target_channel):
                raise Failure('retained channel does not match scanned target')
        ap_attempted = True
        report['ap_on_attempted'] = True
        set_ap(transport, protocol, token, True)
        sleep(10)
        radio = request(transport, protocol, token, RADIO, fields={'form': 'wireless_2g'})
        if radio.get('wireless_2g_enable') != 'on' or radio.get('wireless_2g_disabled_all') != 'off':
            raise Failure('AP-on readback mismatch')
        report['ap_on_verified'] = True
        ap_ssid = radio.get('wireless_2g_ssid')
        if probe_mesh_start:
            mesh_attempted = True
            report['mesh_on_attempted'] = True
            success(protocol.decrypt(transport.post(MESH, protocol.encrypt('operation=write&enable=on'), token)), 'mesh-on')
            sleep(15)
            if read(MESH).get('enable') != 'on':
                raise Failure('Mesh-on readback mismatch')
            report['mesh_on_verified'] = True
        if restart_sta:
            sta_restart_attempted = True
            report['sta_restart_attempted'] = True
            success(protocol.decrypt(transport.post(STA,
                protocol.encrypt('operation=write&enable_2g=off&enable_5g=off'), token)), 'sta-stop')
            sleep(3)
            if read(STA).get('enable_2g') != 'off':
                raise Failure('STA-stop readback mismatch')
            report['sta_stop_verified'] = True
        success(protocol.decrypt(transport.post(STA,
            protocol.encrypt(urlencode({'operation': 'write', **saved})), token)), 'sta-reapply')
        stage('2.4GHz AP is on and STA reapplied; observe the parent wireless client list now')
        sleep(60)
        if scan_observer:
            report['pc_scan_with_ap_on'] = scan_observer(ap_ssid)
        report['ap_on_diagnostics'] = {}
        observe_authenticated(transport, protocol, token, probe_mesh=True, probe_radio=True,
            probe_survey=True, survey_band='2g', probe_status=True, report=report['ap_on_diagnostics'])
        current = read(STA)
        report['sta_fields_preserved_with_ap_on'] = all(current.get(k) == v for k, v in saved.items())
        if observer:
            report['ap_on_ipv4'] = observer.before()
        report['outcome'] = 'ap-start-comparison-complete'
    except Failure as error:
        report['reason'] = str(error)
    except (OSError, subprocess.SubprocessError):
        report['reason'] = 'PC scan operation failed'
    finally:
        if protocol and token and transport.cookie:
            if mesh_attempted:
                try:
                    success(protocol.decrypt(transport.post(MESH, protocol.encrypt('operation=write&enable=off'), token)), 'mesh-off')
                    sleep(15)
                    report['mesh_off_verified'] = request(transport, protocol, token, MESH).get('enable') == 'off'
                except Failure as error:
                    report['mesh_off_verified'] = False
                    report['mesh_off_reason'] = str(error)
            if sta_restart_attempted or mesh_attempted:
                try:
                    success(protocol.decrypt(transport.post(STA,
                        protocol.encrypt(urlencode({'operation': 'write', **saved})), token)), 'sta-on-recovery')
                    sleep(5)
                    current = request(transport, protocol, token, STA)
                    report['sta_on_recovery_verified'] = all(current.get(k) == v for k, v in saved.items())
                except Failure as error:
                    report['sta_on_recovery_verified'] = False
                    report['sta_on_recovery_reason'] = str(error)
            if ap_attempted:
                try:
                    set_ap(transport, protocol, token, False)
                    sleep(10)
                    radio = request(transport, protocol, token, RADIO, fields={'form': 'wireless_2g'})
                    if radio.get('wireless_2g_enable') != 'off' or radio.get('wireless_2g_disabled_all') != 'off':
                        raise Failure('AP-off readback mismatch')
                    report['ap_off'] = 'verified'
                    if mesh_attempted:
                        form = 'wireless_5g'
                        success(protocol.decrypt(transport.post('/admin/wireless?form=' + form,
                            protocol.encrypt(urlencode({'operation': 'write', 'form': form,
                                form + '_enable': 'off', form + '_disabled_all': 'off'})), token)), '5g-ap-off')
                        sleep(5)
                        radio5 = request(transport, protocol, token, '/admin/wireless?form=' + form, fields={'form': form})
                        report['ap_5g_off_verified'] = radio5.get(form + '_enable') == 'off' and radio5.get(form + '_disabled_all') == 'off'
                    current = request(transport, protocol, token, STA)
                    report['sta_fields_preserved_after_ap_off'] = all(current.get(k) == v for k, v in saved.items())
                    report['ap_off_diagnostics'] = {}
                    observe_authenticated(transport, protocol, token, probe_mesh=True, probe_radio=True,
                        report=report['ap_off_diagnostics'])
                except Failure as error:
                    report['ap_off_reason'] = str(error)
                    if report['ap_off'] != 'verified':
                        report['ap_off'] = 'unverified'
                stage('AP-on comparison finished; check the report for AP-off readback')
            try:
                success(protocol.decrypt(transport.post(LOGOUT, protocol.encrypt(''), token)), 'logout')
                report['logout'] = 'complete'
            except Failure:
                report['logout'] = 'failed'
        transport.cookie = ''
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe-ap-start', action='store_true', required=True)
    parser.add_argument('--restart-sta', action='store_true', help='explicitly stop and restart STA while retaining its saved profile')
    parser.add_argument('--probe-mesh-start', action='store_true', help='temporarily enable BE5000 Mesh service, then verify it is off again')
    args = parser.parse_args()
    node = shutil.which('node')
    if not node or not sys.stdin.isatty() or not sys.stderr.isatty():
        print('Stopped: Node.js and interactive terminal are required', file=sys.stderr)
        return 1
    refresh_wifi_scan()
    scan = subprocess.run(['netsh', 'wlan', 'show', 'networks', 'mode=bssid'], capture_output=True, timeout=10, check=False)
    if scan.returncode or len(scan.stdout) > 1048576:
        print('Stopped: PC scan failed', file=sys.stderr)
        return 1
    try:
        _, channel = select_target(scan.stdout.decode('utf8', errors='replace'), 'nisin2.4', '2g')
    except Failure as error:
        print('Stopped: ' + str(error), file=sys.stderr)
        return 1
    report = probe(Transport('192.168.1.52', '192.168.1.1'), Crypto(node), prompt_password,
                   observer=DhcpObserver(), stage=print, target_channel=channel,
                   scan_observer=scan_visibility, restart_sta=args.restart_sta, probe_mesh_start=args.probe_mesh_start)
    stamp = datetime.datetime.now(datetime.timezone.utc)
    report['captured_at'] = stamp.isoformat()
    path = ROOT / 'local-evidence' / ('sta-ap-start-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    write_report(path, report)
    print('Outcome: ' + report['outcome'])
    print('AP off: ' + report['ap_off'])
    print('Report: ' + str(path))
    verified = (report['outcome'] == 'ap-start-comparison-complete' and report['ap_off'] == 'verified'
                and report.get('sta_fields_preserved_after_ap_off') is True)
    if args.probe_mesh_start:
        verified = verified and report.get('mesh_off_verified') is True and report.get('ap_5g_off_verified') is True
    return 0 if verified else 1


if __name__ == '__main__':
    raise SystemExit(main())

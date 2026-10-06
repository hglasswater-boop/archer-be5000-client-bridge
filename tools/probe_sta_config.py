"""Time-limited normal-auth 5GHz STA setter probe with explicit rollback."""
import argparse
import datetime
import getpass
import re
import shutil
import sys
import time
from urllib.parse import urlencode

from .read_sta_state import (Crypto, Failure, LOGOUT, ROOT, Transport, login_session,
                             prompt_password, success, write_report)

STA = '/admin/wireless?form=wireless_connect_to_network'
FIELDS = ('enable_5g', 'ssid_5g', 'encryption_5g', 'psk_version_5g',
          'psk_cipher_5g', 'psk_key_5g')


SECURITY_PLANS = {
    # These are the frontend's mappings. The transition path does not by
    # itself prove that the driver negotiated MLO.
    'wpa2': ('psk', 'rsn', 'aes'),
    'wpa3-transition': ('psk_sae', 'sae_transition', 'aes'),
}


def connection_plan(ssid, psk, security='wpa2'):
    # wifix command construction is vendor code. Reject shell metacharacters.
    if not isinstance(ssid, str) or not re.fullmatch(r'[A-Za-z0-9_.@+ -]{1,32}', ssid):
        raise Failure('SSID is outside the limited safe ASCII format')
    if not isinstance(psk, str) or not re.fullmatch(r'[A-Za-z0-9_.@+-]{8,63}', psk):
        raise Failure('Wi-Fi password is outside the limited safe ASCII format')
    try:
        encryption, psk_version, psk_cipher = SECURITY_PLANS[security]
    except (KeyError, TypeError):
        raise Failure('unsupported Wi-Fi security profile')
    return dict(zip(FIELDS, ('on', ssid, encryption, psk_version, psk_cipher, psk)))


def original_state(state):
    expected = {'enable_2g': 'off', 'enable_5g': 'off',
                'encryption_5g': 'psk', 'psk_version_5g': 'rsn', 'psk_cipher_5g': 'aes',
                'wds_mode_5g': '2', 'locktoap_5g': 'off'}
    if not isinstance(state, dict):
        raise Failure('STA baseline must be a configuration object')
    mismatched = [k for k, v in expected.items() if state.get(k) != v]
    if mismatched:
        raise Failure('STA baseline mismatch in fields: ' + ', '.join(mismatched))
    # Rootap psk_key has no cvt in the mapping; get_option reads UCI directly.
    # Retain RAM copies only and reject masked or unsafe rollback values.
    ssid, psk = state.get('ssid_5g'), state.get('psk_key_5g')
    if not isinstance(ssid, str) or not (ssid == '' or re.fullmatch(r'[A-Za-z0-9_.@+-]{1,32}', ssid)):
        raise Failure('saved STA SSID cannot be restored by this limited probe')
    if not isinstance(psk, str) or not (psk == '' or re.fullmatch(r'[A-Za-z0-9_.@+-]{8,63}', psk)):
        raise Failure('saved STA password cannot be restored by this limited probe')
    return {k: state[k] for k in FIELDS}


def request(transport, protocol, token, route, operation='read', fields=None):
    if operation == 'write' and (route != STA or not fields or set(fields) - set(FIELDS)):
        raise Failure('write is outside the STA field allowlist')
    if operation not in ('read', 'write'):
        raise Failure('operation is not allowed')
    body = urlencode({'operation': operation, **(fields or {})})
    data = success(protocol.decrypt(transport.post(route, protocol.encrypt(body), token)), operation)
    if operation == 'read' and not isinstance(data, dict):
        raise Failure('getter response must be an object')
    return data


def probe(transport, crypto, admin_provider, network_provider, *, sleep=time.sleep,
          observe=lambda: time.sleep(45), stage=lambda text: None, ipv6=None,
          security='wpa2'):
    report = {'outcome': 'stopped', 'write_attempted': False, 'rollback': 'not-needed',
              'logout': 'not-needed', 'association': 'not-measured', 'forwarding': 'not-measured'}
    protocol, token, original = None, '', None
    try:
        config = success(transport.post('/device_config?form=config', b'operation=read'), 'preflight')
        if not isinstance(config, dict) or config.get('certification') != ['SG CLS L1 STAGE2'] or (
                config.get('supportJPFeatures') is not True or
                config.get('supportOperationMode') != ['router', 'ap']):
            raise Failure('device feature/protocol mismatch')
        protocol, token = login_session(transport, crypto, admin_provider)
        read = lambda route: request(transport, protocol, token, route)
        if read('/admin/system?form=sysmode').get('mode') != 'router':
            raise Failure('router mode is required')
        if read('/admin/network?form=lan_ipv4').get('ipaddr') != '192.168.1.1':
            raise Failure('isolated management IP is required')
        if read('/admin/dhcps?form=setting').get('enable') != 'off':
            raise Failure('router DHCP must be off before enabling STA')
        original = original_state(read(STA))
        if ipv6 is not None:
            report['ipv6_before'] = ipv6.before()
        ssid, psk = network_provider()
        plan = connection_plan(ssid, psk, security)
        del ssid, psk
        report['write_attempted'] = True
        request(transport, protocol, token, STA, 'write', plan)
        report['write_accepted'] = True
        sleep(4)
        state = read(STA)
        if any(state.get(k) != v for k, v in plan.items()) or state.get('enable_2g') != 'off':
            raise Failure('STA configuration readback differs from the requested fields')
        report['configuration_verified'] = True
        stage('STA configuration verified; observation window: up to 45 seconds')
        if ipv6 is not None:
            report['ipv6_enabled'] = ipv6.enabled()
            report['forwarding'] = 'IPv6-link-local-probe-only'
        else:
            observe()
        report['outcome'] = 'configuration-probe-complete'
    except Failure as error:
        report['reason'] = str(error)
    except KeyboardInterrupt:
        report['reason'] = 'interrupted; rollback requested'
    finally:
        if report['write_attempted'] and original is not None:
            report['rollback'] = 'failed'
            try:
                request(transport, protocol, token, STA, 'write', {'enable_5g': 'off'})
                report['disable_accepted'] = True
            except Failure:
                report['disable_accepted'] = False
            try:
                request(transport, protocol, token, STA, 'write', original)
                report['restore_accepted'] = True
            except Failure as error:
                report['restore_accepted'] = False
                report['rollback_write_reason'] = str(error)
            try:
                sleep(4)
                restored = request(transport, protocol, token, STA)
                report['sta_disabled'] = restored.get('enable_5g') == 'off'
                if any(restored.get(k) != v for k, v in original.items()) or restored.get('enable_2g') != 'off':
                    raise Failure('rollback readback differs from the initial configuration')
                report['rollback'] = 'verified'
            except Failure as error:
                report['rollback_reason'] = str(error)
            if report['rollback'] == 'verified' and ipv6 is not None:
                try:
                    report['ipv6_after'] = ipv6.after()
                except Failure:
                    report['ipv6_after'] = {'measurement': 'failed'}
        if protocol and token and transport.cookie:
            try:
                success(protocol.decrypt(transport.post(LOGOUT, protocol.encrypt(''), token)), 'logout')
                report['logout'] = 'complete'
            except Failure:
                report['logout'] = 'failed'
        transport.cookie = ''
    return report


def prompt_network():
    return getpass.getpass('Target SSID (hidden): '), getpass.getpass('Existing Wi-Fi password (hidden): ')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='perform the bounded write and rollback probe')
    parser.add_argument('--source-ip', choices=('192.168.1.52',))
    parser.add_argument('--node', default=shutil.which('node'))
    parser.add_argument('--probe-ipv6', action='store_true', help='synchronously measure scoped link-local ping while enabled')
    parser.add_argument('--security', choices=tuple(SECURITY_PLANS), default='wpa2',
                        help='frontend security mapping; wpa3-transition is WPA2/WPA3 mixed')
    args = parser.parse_args(argv)
    if not args.apply:
        print('Plan only: 5GHz ' + args.security + ' candidate, 45-second observation, disable and restore; no network requests')
        return 0
    try:
        if not args.source_ip or not args.node or not sys.stdin.isatty() or not sys.stderr.isatty():
            raise Failure('explicit source, Node.js and interactive terminal are required')
        transport = Transport(args.source_ip, '192.168.1.1')
        ipv6 = None
        if args.probe_ipv6:
            from .sta_ipv6_probe import IPv6Probe, endpoints
            ipv6 = IPv6Probe(*endpoints())
        report = probe(transport, Crypto(args.node), prompt_password, prompt_network,
                       stage=lambda message: print('Stage: ' + message, flush=True), ipv6=ipv6,
                       security=args.security)
        stamp = datetime.datetime.now(datetime.timezone.utc)
        report.update(captured_at=stamp.isoformat(), target=transport.target_ip, source_ip=transport.source_ip)
        path = ROOT / 'local-evidence' / ('sta-probe-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
        write_report(path, report)
        print('Outcome: ' + report['outcome'])
        print('Rollback: ' + report['rollback'])
        if 'reason' in report:
            print('Reason: ' + report['reason'])
        print('Report: ' + str(path))
        return 0 if report['outcome'] == 'configuration-probe-complete' and report['rollback'] == 'verified' else 1
    except Failure as error:
        print('Stopped: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

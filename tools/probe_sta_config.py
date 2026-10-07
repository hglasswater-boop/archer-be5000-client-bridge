"""Normal-auth 5GHz STA setter probe with rollback or explicit retained state."""
import argparse
import datetime
import getpass
import re
import shutil
import sys
import time
from urllib.parse import urlencode

from .read_sta_state import (Crypto, Failure, LOGOUT, ROOT, STATUS_ROUTE, Transport, login_session,
                             prompt_password, success, write_report)

STA = '/admin/wireless?form=wireless_connect_to_network'
STATUS = STATUS_ROUTE
FIELDS = ('enable_5g', 'ssid_5g', 'encryption_5g', 'psk_version_5g',
          'psk_cipher_5g', 'psk_key_5g')


SECURITY_PLANS = {
    # These are the frontend's mappings. The transition path does not by
    # itself prove that the driver negotiated MLO.
    'wpa2': ('psk', 'rsn', 'aes'),
    'wpa3-transition': ('psk_sae', 'sae_transition', 'aes'),
    'wpa3': ('psk_sae', 'sae_only', 'aes'),
}
STATUS_FIELDS = ('connect_status', 'connected_5g', 'status_5g')
SAFE_STATUS_VALUES = frozenset(('connected', 'connecting', 'disconnected', 'disabled', 'enabled', 'on', 'off'))


def status_observation(state):
    """Return only a fixed-label observation from the STA getter."""
    if not isinstance(state, dict):
        return {'field': 'unavailable'}
    for field in STATUS_FIELDS:
        if field not in state:
            continue
        value = state[field]
        if type(value) is bool:
            return {'field': field, 'value': 'on' if value else 'off'}
        if isinstance(value, str):
            return {'field': field, 'value': value if value in SAFE_STATUS_VALUES else 'present'}
        return {'field': field, 'value': 'present'}
    return {'field': 'unavailable'}


def read_status(read):
    try:
        return status_observation(read(STATUS))
    except Failure:
        return {'field': 'read-failed'}


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


def original_state(state, allow_active=False):
    expected = {'enable_2g': 'off', 'enable_5g': 'off',
                'encryption_5g': 'psk', 'psk_version_5g': 'rsn', 'psk_cipher_5g': 'aes',
                'wds_mode_5g': '2', 'locktoap_5g': 'off'}
    if not isinstance(state, dict):
        raise Failure('STA baseline must be a configuration object')
    if allow_active:
        expected['enable_5g'] = 'on'
        if tuple(state.get(k) for k in ('encryption_5g', 'psk_version_5g', 'psk_cipher_5g')) not in SECURITY_PLANS.values():
            raise Failure('active STA security profile is outside the known mappings')
        for key in ('encryption_5g', 'psk_version_5g', 'psk_cipher_5g'):
            expected[key] = state[key]
    mismatched = [k for k, v in expected.items() if state.get(k) != v]
    if mismatched:
        raise Failure('STA baseline mismatch in fields: ' + ', '.join(mismatched))
    # Rootap psk_key has no cvt in the mapping; get_option reads UCI directly.
    # Retain RAM copies only and reject masked or unsafe rollback values.
    ssid, psk = state.get('ssid_5g'), state.get('psk_key_5g')
    saved_format = r'[A-Za-z0-9_.@+ -]{1,32}' if allow_active else r'[A-Za-z0-9_.@+-]{1,32}'
    if not isinstance(ssid, str) or not (ssid == '' or re.fullmatch(saved_format, ssid)):
        raise Failure('saved STA SSID cannot be restored by this limited probe')
    if not isinstance(psk, str) or not (psk == '' or re.fullmatch(r'[A-Za-z0-9_.@+-]{8,63}', psk)):
        raise Failure('saved STA password cannot be restored by this limited probe')
    if allow_active and (not ssid or not psk):
        raise Failure('active STA must have restorable saved credentials')
    return {k: state[k] for k in FIELDS}


def request(transport, protocol, token, route, operation='read', fields=None):
    if operation == 'write' and (route != STA or not fields or set(fields) - set(FIELDS)):
        raise Failure('write is outside the STA field allowlist')
    if operation not in ('read', 'write', 'tmp_read') or (
            operation == 'tmp_read' and (route != STA or fields)):
        raise Failure('operation is not allowed')
    body = urlencode({'operation': operation, **(fields or {})})
    data = success(protocol.decrypt(transport.post(route, protocol.encrypt(body), token)), operation)
    if operation in ('read', 'tmp_read') and not isinstance(data, dict):
        raise Failure('getter response must be an object')
    return data


def link_observation(state):
    """Keep only fixed-label/limited numeric observations, never identifiers."""
    if not isinstance(state, dict):
        raise Failure('link observation must be an object')
    result = {}
    for band in ('2g', '5g'):
        mac = state.get('bssid_' + band)
        if isinstance(mac, str) and re.fullmatch(r'(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', mac):
            result['bssid_present_' + band] = bool(int(mac.replace(':', '').replace('-', ''), 16))
        for kind, limit in (('signal', 3), ('channel', 233)):
            value = state.get(kind + '_' + band)
            if isinstance(value, str) and re.fullmatch(r'[0-9]{1,3}', value):
                value = int(value)
            if type(value) is int and 0 <= value <= limit:
                result[kind + '_' + band] = value
    status = state.get('internet_status')
    if status in ('connected', 'disconnected'):
        result['internet_status'] = status
    return result


def probe(transport, crypto, admin_provider, network_provider, *, sleep=time.sleep,
          observe=lambda: time.sleep(45), stage=lambda text: None, ipv6=None,
          security='wpa2', ipv4=None, probe_link=False, keep_enabled=False, replace_active=False):
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
        if replace_active and not keep_enabled:
            raise Failure('active replacement requires retained-state mode')
        original = original_state(read(STA), allow_active=replace_active)
        link_read = lambda: link_observation(request(transport, protocol, token, STA, 'tmp_read'))
        if probe_link:
            report['link_before'] = link_read()
        if ipv6 is not None:
            report['ipv6_before'] = ipv6.before()
        if ipv4 is not None:
            report['ipv4_before'] = ipv4.before()
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
        report['status_after_write'] = read_status(read)
        stage('STA configuration verified; observation window: up to 45 seconds')
        if ipv4 is not None:
            sleep(10)
            report['ipv4_enabled'] = ipv4.enabled()
            report['forwarding'] = 'IPv4-DHCP-DISCOVER-OFFER-only'
        elif ipv6 is not None:
            report['ipv6_enabled'] = ipv6.enabled()
            report['forwarding'] = 'IPv6-link-local-probe-only'
        else:
            observe()
        if probe_link:
            report['link_enabled'] = link_read()
        report['outcome'] = 'configuration-probe-complete'
    except Failure as error:
        report['reason'] = str(error)
    except KeyboardInterrupt:
        report['reason'] = 'interrupted; rollback requested'
    finally:
        if keep_enabled and report.get('configuration_verified'):
            report['rollback'] = 'not-requested'
            report['sta_kept_enabled'] = True
        elif report['write_attempted'] and original is not None:
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
                report['status_after_restore'] = read_status(read)
            except Failure as error:
                report['rollback_reason'] = str(error)
            if report['rollback'] == 'verified' and ipv6 is not None:
                try:
                    report['ipv6_after'] = ipv6.after()
                except Failure:
                    report['ipv6_after'] = {'measurement': 'failed'}
            if report['rollback'] == 'verified' and ipv4 is not None:
                try:
                    report['ipv4_after'] = ipv4.after()
                except Failure:
                    report['ipv4_after'] = {'measurement': 'failed'}
            if report['rollback'] == 'verified' and probe_link:
                try:
                    report['link_after'] = link_read()
                except Failure:
                    report['link_after'] = {'measurement': 'failed'}
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
    parser.add_argument('--probe-ipv4', action='store_true', help='one interface-verified DHCP DISCOVER/OFFER observation per phase, no lease')
    parser.add_argument('--probe-link', action='store_true', help='bounded known tmp_read observations; no identifiers saved')
    parser.add_argument('--keep-enabled', action='store_true', help='keep verified STA settings enabled after observation; restore only on failed configuration readback')
    parser.add_argument('--replace-active', action='store_true', help='replace an active known STA profile; requires --keep-enabled')
    parser.add_argument('--security', choices=tuple(SECURITY_PLANS), default='wpa2',
                        help='known security mapping; wpa3 is SAE only, wpa3-transition is mixed')
    args = parser.parse_args(argv)
    if not args.apply:
        finish = 'keep verified STA enabled' if args.keep_enabled else 'disable and restore'
        print('Plan only: 5GHz ' + args.security + ' candidate, bounded observation, ' + finish + '; no network requests')
        return 0
    try:
        if not args.source_ip or not args.node or not sys.stdin.isatty() or not sys.stderr.isatty():
            raise Failure('explicit source, Node.js and interactive terminal are required')
        transport = Transport(args.source_ip, '192.168.1.1')
        if sum((args.probe_ipv4, args.probe_ipv6, args.probe_link)) > 1:
            raise Failure('choose one observation protocol')
        ipv6 = None
        ipv4 = None
        if args.probe_ipv4:
            from .sta_ipv4_probe import DhcpObserver
            ipv4 = DhcpObserver()
        if args.probe_ipv6:
            from .sta_ipv6_probe import IPv6Probe, endpoints
            ipv6 = IPv6Probe(*endpoints())
        report = probe(transport, Crypto(args.node), prompt_password, prompt_network,
                       stage=lambda message: print('Stage: ' + message, flush=True), ipv6=ipv6,
                       security=args.security, ipv4=ipv4, probe_link=args.probe_link,
                       keep_enabled=args.keep_enabled, replace_active=args.replace_active)
        stamp = datetime.datetime.now(datetime.timezone.utc)
        report.update(captured_at=stamp.isoformat(), target=transport.target_ip, source_ip=transport.source_ip)
        path = ROOT / 'local-evidence' / ('sta-probe-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
        write_report(path, report)
        print('Outcome: ' + report['outcome'])
        print('Rollback: ' + report['rollback'])
        if 'reason' in report:
            print('Reason: ' + report['reason'])
        print('Report: ' + str(path))
        return 0 if report['outcome'] == 'configuration-probe-complete' and (
            report['rollback'] == 'verified' or report.get('sta_kept_enabled')) else 1
    except Failure as error:
        print('Stopped: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

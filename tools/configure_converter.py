"""Disable the normal Mesh setting and reapply retained STA; no routine restore."""
import argparse
import datetime
import shutil
import sys
import time
from urllib.parse import urlencode

from .probe_sta_config import STA, original_state, request
from .read_sta_diagnostics import MESH
from .read_sta_state import Crypto, Failure, LOGOUT, ROOT, Transport, login_session, prompt_password, success, write_report
from .sta_ipv4_probe import DhcpObserver


def mesh_off(transport, protocol, token):
    return success(protocol.decrypt(transport.post(MESH,
        protocol.encrypt('operation=write&enable=off'), token)), 'mesh-off')


def ap_off(transport, protocol, token, band):
    if band not in ('2g', '5g'):
        raise Failure('AP band outside converter plan')
    form = 'wireless_' + band
    body = urlencode({'operation': 'write', 'form': form, form + '_enable': 'off',
                      form + '_disabled_all': 'off'})
    return success(protocol.decrypt(transport.post('/admin/wireless?form=' + form,
                                                   protocol.encrypt(body), token)), 'ap-off')


def configure(transport, crypto, provider, *, sleep=time.sleep, observer=None, stage=lambda s: None,
              disable_aps=False):
    report = {'outcome': 'stopped', 'logout': 'not-needed', 'association': 'not-measured'}
    protocol, token = None, ''
    try:
        protocol, token = login_session(transport, crypto, provider)
        read = lambda route: request(transport, protocol, token, route)
        def management():
            if read('/admin/system?form=sysmode').get('mode') != 'router' or (
                read('/admin/network?form=lan_ipv4').get('ipaddr') != '192.168.1.1' or
                read('/admin/dhcps?form=setting').get('enable') != 'off'):
                raise Failure('converter management precondition mismatch')
        management()
        saved = original_state(read(STA), allow_active=True)
        enabled = read(MESH).get('enable')
        if enabled not in ('on', 'off'):
            raise Failure('unknown mesh enable state')
        if enabled == 'on':
            report['mesh_write_attempted'] = True
            mesh_off(transport, protocol, token)
            report['mesh_write_accepted'] = True
            stage('Mesh setting saved off; waiting for normal service update')
            sleep(15)
        report['mesh_off_verified'] = read(MESH).get('enable') == 'off'
        if not report['mesh_off_verified']:
            raise Failure('mesh-off readback mismatch')
        management()
        report['management_verified'] = True
        if disable_aps:
            report['ap_off'] = {}
            for band in ('2g', '5g'):
                form = 'wireless_' + band
                route = '/admin/wireless?form=' + form
                ap_off(transport, protocol, token, band)
                stage('AP ' + band + ' disable requested; waiting for VAP update')
                sleep(10)
                state = request(transport, protocol, token, route, fields={'form': form})
                verified = state.get(form + '_enable') == 'off'
                report['ap_off'][band] = verified
                if not verified or state.get(form + '_disabled_all') != 'off':
                    raise Failure('AP-off or radio-preservation readback mismatch')
            management()
        report['sta_write_attempted'] = True
        request(transport, protocol, token, STA, 'write', saved)
        stage('Retained STA reapplied; waiting for radio update')
        sleep(15)
        current = read(STA)
        report['sta_configuration_verified'] = all(current.get(k) == v for k, v in saved.items())
        report['sta_kept_enabled'] = current.get('enable_5g') == 'on'
        if not report['sta_configuration_verified'] or current.get('enable_2g') != 'off':
            raise Failure('retained STA readback mismatch')
        if observer:
            report['ipv4'] = observer.before()
        report['outcome'] = 'mesh-off-sta-retained'
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply-mesh-off', action='store_true', required=True)
    p.add_argument('--disable-aps', action='store_true', help='disable ordinary 2.4/5GHz AP VAPs, preserve radio')
    args = p.parse_args()
    node = shutil.which('node')
    if not node or not sys.stdin.isatty() or not sys.stderr.isatty():
        print('Stopped: Node.js and interactive terminal are required', file=sys.stderr)
        return 1
    report = configure(Transport('192.168.1.52', '192.168.1.1'), Crypto(node), prompt_password,
                       observer=DhcpObserver(), stage=print, disable_aps=args.disable_aps)
    stamp = datetime.datetime.now(datetime.timezone.utc)
    report['captured_at'] = stamp.isoformat()
    path = ROOT / 'local-evidence' / ('converter-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    write_report(path, report)
    print('Outcome: ' + report['outcome'])
    print('Report: ' + str(path))
    return 0 if report['outcome'] == 'mesh-off-sta-retained' else 1


if __name__ == '__main__':
    raise SystemExit(main())

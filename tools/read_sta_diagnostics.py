"""Known read-only STA observation and sanitized public-system-log summary."""
import argparse
import datetime
import re
import shutil
import sys

from .probe_sta_config import STA, link_observation, request
from .read_sta_state import Crypto, Failure, LOGOUT, ROOT, Transport, login_session, prompt_password, success, write_report

SYSLOG = '/admin/syslog?form=log'
MESH = '/admin/easymesh?form=easymesh_enable'
SURVEY = '/admin/wireless?form=survey_5g'
RADIO = '/admin/wireless?form=wireless_5g'
PATTERNS = {
    'apcli': r'apcli|rootap|wifix',
    'supplicant': r'wpa_supplicant|wpa_cli',
    'association': r'associat|接続',
    'authentication': r'authenticat|handshake|認証',
    'disconnection': r'disconnect|deauth|切断',
    'failure': r'fail|error|invalid|失敗|エラー',
}


def summarize_log(data):
    if not isinstance(data, list) or len(data) > 4096:
        raise Failure('system log must be a bounded row list')
    summary = {'rows': len(data), 'content_rows': 0, 'matches': {k: 0 for k in PATTERNS}, 'wifi_error_rows': 0}
    for row in data:
        if not isinstance(row, dict):
            continue
        content = row.get('content')
        if not isinstance(content, str) or len(content) > 8192:
            continue
        summary['content_rows'] += 1
        matches = {k: bool(re.search(pattern, content, re.I)) for k, pattern in PATTERNS.items()}
        for k, matched in matches.items():
            summary['matches'][k] += int(matched)
        wifi = bool(re.search(r'apcli|rootap|wifix|wpa_|wireless|wi.?fi|無線', content, re.I))
        summary['wifi_error_rows'] += int(wifi and matches['failure'])
    return summary


def mesh_observation(data):
    if not isinstance(data, dict):
        raise Failure('mesh setting must be an object')
    value = data.get('enable')
    return {'enable': value if value in ('on', 'off') else 'unavailable'}


def summarize_survey(data, target):
    # Lua's empty array is encoded as an empty object by this firmware.
    if data == {}:
        data = []
    if not isinstance(data, list) or len(data) > 4096:
        raise Failure('survey must be a bounded row list')
    matches = [r for r in data if isinstance(r, dict) and r.get('ssid') == target and target]
    targets = []
    for row in matches:
        value = {}
        for name, bound in (('channel', 233), ('signal', 100)):
            v = row.get(name)
            if isinstance(v, str) and re.fullmatch(r'[0-9]{1,3}', v):
                v = int(v)
            if type(v) is int and 0 <= v <= bound:
                value[name] = v
        for name, allowed in [('encryption', ('none', 'wep', 'psk', 'psk_sae')),
                              ('psk_version', ('auto', 'wpa', 'rsn', 'sae_transition', 'sae_only')),
                              ('psk_cipher', ('auto', 'aes', 'ccmp', 'tkip'))]:
            if row.get(name) in allowed:
                value[name] = row[name]
        targets.append(value)
    return {'rows': len(data), 'target_matches': len(matches), 'targets': targets}


def radio_observation(data):
    if not isinstance(data, dict):
        raise Failure('radio setting must be an object')
    result = {}
    for key in ('wireless_5g_enable', 'wireless_5g_disabled_all', 'radio_5g_enable'):
        if data.get(key) in ('on', 'off'):
            result[key] = data[key]
    for key in ('radio_5g_channel', 'wireless_5g_channel'):
        value = data.get(key)
        if isinstance(value, str) and re.fullmatch(r'[0-9]{1,3}', value):
            value = int(value)
        if type(value) is int and 0 <= value <= 233:
            result[key] = value
        elif value == 'auto':
            result[key] = 'auto'
    return result


def collect(transport, crypto, password_provider, *, probe_mesh=False, probe_survey=False, probe_radio=False):
    report = {'outcome': 'stopped', 'logout': 'not-needed'}
    protocol, token = None, ''
    try:
        protocol, token = login_session(transport, crypto, password_provider)
        config = request(transport, protocol, token, STA)
        report['sta_5g_enabled'] = config.get('enable_5g') == 'on'
        if probe_radio:
            report['radio_5g'] = radio_observation(request(transport, protocol, token, RADIO,
                                                          fields={'form': 'wireless_5g'}))
        if probe_survey:
            payload = protocol.encrypt('operation=read')
            rows = success(protocol.decrypt(transport.post(SURVEY, payload, token)), 'survey')
            report['survey_5g'] = summarize_survey(rows, config.get('ssid_5g'))
        if probe_mesh:
            report['mesh_setting'] = mesh_observation(request(transport, protocol, token, MESH))
        report['link'] = link_observation(request(transport, protocol, token, STA, 'tmp_read'))
        filter_state = request(transport, protocol, token, '/admin/syslog?form=filter')
        report['log_filter'] = {
            'all_types': filter_state.get('type') == 'ALL',
            'all_levels': filter_state.get('level') == 'ALL',
        }
        body = protocol.encrypt('operation=load')
        data = success(protocol.decrypt(transport.post(SYSLOG, body, token)), 'system-log-read')
        report['system_log'] = summarize_log(data)
        report['outcome'] = 'diagnostics-complete'
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-ip', required=True, choices=('192.168.1.52',))
    parser.add_argument('--probe-mesh', action='store_true', help='read known EasyMesh enable getter; no settings changes')
    parser.add_argument('--probe-survey', action='store_true', help='scan 5GHz and summarize saved-target matches')
    parser.add_argument('--probe-radio', action='store_true', help='read limited 5GHz AP/radio configuration')
    args = parser.parse_args()
    node = shutil.which('node')
    if not node or not sys.stdin.isatty() or not sys.stderr.isatty():
        print('Stopped: Node.js and interactive terminal are required', file=sys.stderr)
        return 1
    report = collect(Transport(args.source_ip, '192.168.1.1'), Crypto(node), prompt_password,
                     probe_mesh=args.probe_mesh, probe_survey=args.probe_survey, probe_radio=args.probe_radio)
    stamp = datetime.datetime.now(datetime.timezone.utc)
    report['captured_at'] = stamp.isoformat()
    path = ROOT / 'local-evidence' / ('sta-diagnostics-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    write_report(path, report)
    print('Outcome: ' + report['outcome'])
    print('Report: ' + str(path))
    return 0 if report['outcome'] == 'diagnostics-complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())

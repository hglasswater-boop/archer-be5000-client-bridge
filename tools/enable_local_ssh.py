"""Normal-auth request to allow this wired PC's local SSH access only."""
import datetime
import shutil
import sys
from .read_sta_state import Crypto, Failure, LOGOUT, LOCAL_SSH_ROUTE, ROOT, Transport, login_session, prompt_password, success, write_report

ROUTE = LOCAL_SSH_ROUTE


def enable_local_ssh(transport, protocol, token):
    success(protocol.decrypt(transport.post(ROUTE,
        protocol.encrypt('operation=app_user_agree&ssh_is_enable=1'), token)), 'local-ssh-enable')
    return True


def main():
    node = shutil.which('node')
    if not node or not sys.stdin.isatty() or not sys.stderr.isatty():
        print('Stopped: Node.js and interactive terminal are required', file=sys.stderr)
        return 1
    transport = Transport('192.168.1.52', '192.168.1.1')
    report = {'outcome': 'stopped', 'logout': 'not-needed'}
    protocol, token = None, ''
    try:
        protocol, token = login_session(transport, Crypto(node), prompt_password)
        report['local_ssh_permission_accepted'] = enable_local_ssh(transport, protocol, token) is True
        if not report['local_ssh_permission_accepted']:
            raise Failure('local SSH permission returned unexpected value')
        report['outcome'] = 'local-ssh-permission-enabled'
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
    path = ROOT / 'local-evidence' / ('local-ssh-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    write_report(path, report)
    print('Outcome: ' + report['outcome'])
    print('Report: ' + str(path))
    return 0 if report['outcome'] == 'local-ssh-permission-enabled' else 1


if __name__ == '__main__':
    raise SystemExit(main())

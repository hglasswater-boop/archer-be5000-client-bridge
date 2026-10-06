"""Scoped IPv6 link-local controls for the temporary STA configuration probe."""
import datetime
import ipaddress
import json
import os
import re
import subprocess
import time
from pathlib import Path

from .read_sta_state import Failure, ROOT


def scoped(address, interface):
    if not isinstance(address, str) or interface not in (7, 14):
        raise Failure('IPv6 endpoint is outside the measured interfaces')
    parts = address.split('%')
    if len(parts) > 2 or len(parts) == 2 and parts[1] != str(interface):
        raise Failure('IPv6 endpoint scope mismatch')
    try:
        parsed = ipaddress.IPv6Address(parts[0])
    except ValueError:
        raise Failure('IPv6 endpoint must be link-local') from None
    if not parsed.is_link_local:
        raise Failure('IPv6 endpoint must be link-local')
    return str(parsed) + '%' + str(interface)


def endpoints():
    shell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = """$ErrorActionPreference='Stop';
    $e=Get-NetIPAddress -InterfaceIndex 7 -AddressFamily IPv6 | Where-Object { $_.IPAddress -like 'fe80::*' -and [string]$_.AddressState -eq 'Preferred' };
    $w=Get-NetIPAddress -InterfaceIndex 14 -AddressFamily IPv6 | Where-Object { $_.IPAddress -like 'fe80::*' -and [string]$_.AddressState -eq 'Preferred' };
    $g=Get-NetRoute -InterfaceIndex 14 -AddressFamily IPv6 -DestinationPrefix '::/0' | Sort-Object RouteMetric | Select-Object -First 1;
    [pscustomobject]@{ethernet=$e.IPAddress; wifi=$w.IPAddress; peer=$g.NextHop} | ConvertTo-Json -Compress"""
    try:
        result = subprocess.run([str(shell), '-NoProfile', '-Command', script],
                                timeout=10, capture_output=True, check=False)
        if result.returncode or len(result.stdout) > 4096:
            raise ValueError()
        data = json.loads(result.stdout)
        return scoped(data['ethernet'], 7), scoped(data['wifi'], 14), scoped(data['peer'], 14)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise Failure('IPv6 interface baseline unavailable') from None


class IPv6Probe:
    def __init__(self, ethernet, wifi, peer, *, runner=subprocess.run, sleep=time.sleep):
        self.ethernet = scoped(ethernet, 7)
        self.wifi = scoped(wifi, 14)
        self.peer_wifi = scoped(peer, 14)
        self.peer_ethernet = scoped(self.peer_wifi.split('%')[0], 7)
        self.runner, self.sleep = runner, sleep
        self.ping = str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/ping.exe')
        self.stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        self.directory = ROOT / 'local-evidence'
        if self.directory.is_symlink() or self.directory.resolve().parent != ROOT.resolve():
            raise Failure('IPv6 evidence directory must be inside the repository')
        self.directory.mkdir(exist_ok=True)

    def ping_once(self, name, phase):
        if name not in ('ethernet', 'wifi') or phase not in ('before', 'enabled-1', 'enabled-2', 'enabled-3', 'after'):
            raise Failure('IPv6 measurement label invalid')
        source = self.ethernet if name == 'ethernet' else self.wifi
        target = self.peer_ethernet if name == 'ethernet' else self.peer_wifi
        try:
            result = self.runner([self.ping, '-6', '-S', source, '-n', '2', '-w', '1000', target],
                                 timeout=8, capture_output=True, check=False)
            if len(result.stdout) > 16384 or result.returncode not in (0, 1):
                raise ValueError()
            # Raw addresses are restricted to the ignored local evidence directory.
            path = self.directory / (f'ipv6-{self.stamp}-{phase}-{name}.txt')
            with path.open('xb') as output:
                output.write(result.stdout)
            # A Windows ping exit code alone can include unreachable replies.
            # Require a timed reply from the scoped reference peer itself.
            lines = result.stdout.decode('ascii', errors='ignore').lower().splitlines()
            return result.returncode == 0 and any(target.lower() in line and
                re.search(r'[=<]\s*\d+\s*ms', line) for line in lines)
        except (OSError, subprocess.SubprocessError, ValueError):
            raise Failure('scoped IPv6 measurement failed') from None

    def before(self):
        result = {'ethernet_reply': self.ping_once('ethernet', 'before'),
                  'wifi_control_reply': self.ping_once('wifi', 'before')}
        if not result['wifi_control_reply']:
            raise Failure('Wi-Fi IPv6 reference peer did not reply')
        return result

    def enabled(self):
        result = {'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'ethernet_reply': False, 'attempts': 0}
        for i in range(1, 4):
            result['attempts'] = i
            if self.ping_once('ethernet', 'enabled-' + str(i)):
                result['ethernet_reply'] = True
                break
            if i < 3:
                self.sleep(5)
        return result

    def after(self):
        return {'ethernet_reply': self.ping_once('ethernet', 'after')}

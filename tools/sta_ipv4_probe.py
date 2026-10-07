"""Bounded DHCP DISCOVER/OFFER observation; never requests or applies a lease."""
import ctypes
import json
import os
import secrets
import select
import socket
import struct
import subprocess
import time
import uuid
from pathlib import Path

from .read_sta_state import Failure

MAGIC = b'\x63\x82\x53\x63'


def discover(xid, mac):
    if not isinstance(xid, bytes) or len(xid) != 4 or not isinstance(mac, bytes) or len(mac) != 6:
        raise Failure('DHCP identity format invalid')
    packet = bytearray(236)
    packet[:4] = b'\x01\x01\x06\x00'
    packet[4:8] = xid
    packet[10:12] = b'\x80\x00'  # request a broadcast reply, ciaddr/giaddr stay zero
    packet[28:34] = mac
    packet.extend(MAGIC + b'\x35\x01\x01\x3d\x07\x01' + mac + b'\x37\x03\x01\x03\x36\xff')
    return bytes(packet).ljust(300, b'\x00')


def is_offer(packet, xid, mac):
    if len(packet) < 240 or len(packet) > 4096 or packet[:3] != b'\x02\x01\x06':
        return False
    if packet[4:8] != xid or packet[28:34] != mac or packet[236:240] != MAGIC:
        return False
    options, offset = {}, 240
    while offset < len(packet):
        code = packet[offset]
        offset += 1
        if code == 255:
            break
        if code == 0:
            continue
        if offset >= len(packet):
            return False
        length = packet[offset]
        offset += 1
        if offset + length > len(packet) or code in options:
            return False
        options[code] = packet[offset:offset + length]
        offset += length
    return (options.get(53) == b'\x02' and len(options.get(54, b'')) == 4
            and packet[16:20] != b'\x00' * 4)


def interface_macs():
    shell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = "$ErrorActionPreference='Stop'; Get-NetAdapter | Where-Object { $_.ifIndex -in 7,14 -and [string]$_.Status -eq 'Up' } | Select-Object ifIndex,MacAddress | ConvertTo-Json -Compress"
    try:
        result = subprocess.run([str(shell), '-NoProfile', '-Command', script],
                                capture_output=True, timeout=10, check=True)
        rows = json.loads(result.stdout)
        macs = {row['ifIndex']: bytes.fromhex(row['MacAddress'].replace('-', '')) for row in rows}
        if set(macs) != {7, 14} or any(len(mac) != 6 for mac in macs.values()):
            raise ValueError()
        return macs
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise Failure('DHCP interface baseline unavailable') from None


class WsaBuffer(ctypes.Structure):
    _fields_ = [('length', ctypes.c_uint32), ('buffer', ctypes.c_void_p)]


class WsaMessage(ctypes.Structure):
    _fields_ = [('name', ctypes.c_void_p), ('namelen', ctypes.c_int),
                ('buffers', ctypes.POINTER(WsaBuffer)), ('count', ctypes.c_uint32),
                ('control', WsaBuffer), ('flags', ctypes.c_uint32)]


class ControlHeader(ctypes.Structure):
    _fields_ = [('length', ctypes.c_size_t), ('level', ctypes.c_int), ('kind', ctypes.c_int)]


def received_interface(control):
    alignment = ctypes.sizeof(ctypes.c_size_t)
    header_size = ctypes.sizeof(ControlHeader)
    offset = 0
    while offset + header_size <= len(control):
        header = ControlHeader.from_buffer_copy(control, offset)
        if header.length < header_size or offset + header.length > len(control):
            return None
        if header.level == socket.IPPROTO_IP and header.kind == 19 and header.length >= header_size + 8:
            return struct.unpack_from('=I', control, offset + header_size + 4)[0]
        offset += (header.length + alignment - 1) // alignment * alignment
    return None


class DhcpObserver:
    def __init__(self):
        if os.name != 'nt':
            raise Failure('DHCP observation requires Windows')
        self.macs = interface_macs()
        self.ws = ctypes.WinDLL('Ws2_32.dll')
        self.ws.WSAIoctl.argtypes = [ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p,
                                    ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
                                    ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p, ctypes.c_void_p]
        self.ws.WSAIoctl.restype = ctypes.c_int

    def measure(self, interface):
        if interface not in (7, 14):
            raise Failure('DHCP interface not allowlisted')
        xid, mac = secrets.token_bytes(4), self.macs[interface]
        # A unique transaction, real adapter MAC, one DISCOVER, no REQUEST.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as channel:
            try:
                channel.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                channel.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                channel.setsockopt(socket.IPPROTO_IP, 31, struct.pack('!I', interface))
                channel.setsockopt(socket.IPPROTO_IP, 19, 1)
                channel.bind(('0.0.0.0', 68))
                pointer, count = ctypes.c_void_p(), ctypes.c_uint32()
                guid = ctypes.create_string_buffer(uuid.UUID('f689d7c8-6f1f-436b-8a53-e54fe351c322').bytes_le)
                if self.ws.WSAIoctl(channel.fileno(), 0xC8000006, guid, 16,
                                    ctypes.byref(pointer), ctypes.sizeof(pointer), ctypes.byref(count), None, None):
                    raise OSError()
                receive = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_size_t,
                    ctypes.POINTER(WsaMessage), ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p,
                    ctypes.c_void_p)(pointer.value)
                channel.setblocking(False)
                channel.sendto(discover(xid, mac), ('255.255.255.255', 67))
                deadline, wrong_interface = time.monotonic() + 8, False
                while time.monotonic() < deadline:
                    if not select.select([channel], [], [], max(0, deadline - time.monotonic()))[0]:
                        break
                    payload, control, address = ctypes.create_string_buffer(4096), ctypes.create_string_buffer(128), ctypes.create_string_buffer(32)
                    buffer = WsaBuffer(4096, ctypes.addressof(payload))
                    message = WsaMessage(ctypes.addressof(address), 32, ctypes.pointer(buffer), 1,
                                         WsaBuffer(128, ctypes.addressof(control)), 0)
                    amount = ctypes.c_uint32()
                    if receive(channel.fileno(), ctypes.byref(message), ctypes.byref(amount), None, None):
                        raise OSError()
                    if message.flags & (0x100 | 0x200):  # MSG_TRUNC / MSG_CTRUNC
                        continue
                    if struct.unpack_from('!H', address.raw, 2)[0] != 67:
                        continue
                    if is_offer(payload.raw[:amount.value], xid, mac):
                        incoming = received_interface(control.raw[:message.control.length])
                        if incoming == interface:
                            return {'offer_on_requested_interface': True, 'discover_sent': True,
                                    'lease_requested': False}
                        wrong_interface = True
                return {'offer_on_requested_interface': False, 'discover_sent': True,
                        'lease_requested': False, 'matching_offer_on_other_interface': wrong_interface}
            except OSError:
                raise Failure('DHCP socket observation failed') from None

    def before(self):
        control = self.measure(14)
        if not control['offer_on_requested_interface']:
            raise Failure('Wi-Fi DHCP control did not return an interface-verified OFFER')
        return {'wifi_control': control, 'ethernet': self.measure(7)}

    def enabled(self):
        return self.measure(7)

    def after(self):
        return self.measure(7)

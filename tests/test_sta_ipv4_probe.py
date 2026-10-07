import ctypes
import struct
import unittest

from tools.sta_ipv4_probe import ControlHeader, discover, is_offer, received_interface


class DhcpTests(unittest.TestCase):
    def test_offer_requires_matching_transaction_mac_and_complete_options(self):
        xid, mac = b'1234', bytes(range(6))
        request = discover(xid, mac)
        self.assertEqual(request[240:243], b'\x35\x01\x01')
        self.assertEqual(request[12:28], bytes(16))
        offer = bytearray(request[:240])
        offer[0] = 2
        offer[16:20] = b'\xc0\xa8\x00\x64'
        offer.extend(b'\x35\x01\x02\x36\x04\xc0\xa8\x00\x01\xff')
        self.assertTrue(is_offer(offer, xid, mac))
        self.assertFalse(is_offer(offer, b'5678', mac))
        self.assertFalse(is_offer(offer, xid, bytes([7]) * 6))
        self.assertFalse(is_offer(offer[:247], xid, mac))
        offer[242] = 5  # ACK is not an OFFER
        self.assertFalse(is_offer(offer, xid, mac))

    def test_received_interface_requires_packet_info_and_complete_control_buffer(self):
        header = ControlHeader(ctypes.sizeof(ControlHeader) + 8, 0, 19)
        control = bytes(header) + bytes(4) + struct.pack('=I', 7)
        self.assertEqual(received_interface(control), 7)
        self.assertIsNone(received_interface(control[:-1]))
        header.kind = 1
        self.assertIsNone(received_interface(bytes(header) + control[ctypes.sizeof(header):]))

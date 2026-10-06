import struct
import unittest
import zlib

from tools.read_ubi import read_static_volumes


def block(lnum=0, payload=b'test', used=1, seq=7):
    out = bytearray(b'\xff' * 4096)
    ec = bytearray(64)
    ec[:4] = b'UBI#'
    ec[4] = 1
    struct.pack_into('>III', ec, 16, 64, 128, seq)
    struct.pack_into('>I', ec, 60, ~zlib.crc32(ec[:60]) & 0xffffffff)
    vid = bytearray(64)
    vid[:4] = b'UBI!'
    vid[4:6] = bytes([1, 2])
    struct.pack_into('>II', vid, 8, 2, lnum)
    struct.pack_into('>IIII', vid, 20, len(payload), used, 0, ~zlib.crc32(payload) & 0xffffffff)
    struct.pack_into('>I', vid, 60, ~zlib.crc32(vid[:60]) & 0xffffffff)
    out[:64], out[64:128], out[128:128+len(payload)] = ec, vid, payload
    return bytes(out)


class UbiTests(unittest.TestCase):
    def test_reorders_logical_blocks(self):
        volumes = read_static_volumes(block(1,b'last',2)+block(0,b'first',2),0,4096)
        self.assertEqual(volumes[2], b'firstlast')

    def test_crc_corruption(self):
        for offset in (20, 74, 129):
            b = bytearray(block()); b[offset] ^= 1
            with self.assertRaises(ValueError):
                read_static_volumes(b,0,4096)

    def test_gap(self):
        with self.assertRaises(ValueError):
            read_static_volumes(block(1,used=2),0,4096)

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            read_static_volumes(block()+block(),0,4096)

    def test_sequence_mixture(self):
        with self.assertRaises(ValueError):
            read_static_volumes(block(0,used=2)+block(1,used=2,seq=8),0,4096)

    def test_truncated_extent(self):
        with self.assertRaises(ValueError):
            read_static_volumes(block()[:-1],0,4096)


if __name__ == '__main__':
    unittest.main()

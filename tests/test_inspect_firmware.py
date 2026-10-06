import hashlib
import io
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from tools.inspect_firmware import analyze_bytes, read_image


class FirmwareTests(unittest.TestCase):
    def test_offsets_and_hash_are_of_unmodified_input(self):
        data = b'abc' + b'\x7fELF' + b'padding' + b'\x7fELF'
        report = analyze_bytes(data)
        self.assertEqual(report['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual([x['offset'] for x in report['magic_candidates']], [3, 14])
        self.assertTrue(all(x['status'] == 'candidate' for x in report['magic_candidates']))

    def test_squashfs_extent_and_version_are_checked(self):
        header = bytearray(96)
        header[:4] = b'hsqs'
        struct.pack_into('<HH', header, 28, 4, 0)
        struct.pack_into('<Q', header, 40, 96)
        valid = analyze_bytes(b'abcd' + header)['magic_candidates'][0]
        self.assertTrue(valid['extent_in_bounds'])
        self.assertEqual(valid['bytes_used'], 96)
        struct.pack_into('<Q', header, 40, 10000)
        bad = analyze_bytes(header)['magic_candidates'][0]
        self.assertFalse(bad['extent_in_bounds'])
        self.assertEqual(bad['status'], 'candidate')

    def test_truncated_magic_is_not_a_valid_filesystem(self):
        candidate = analyze_bytes(b'hsqs')['magic_candidates'][0]
        self.assertEqual(candidate['status'], 'truncated_header')

    def test_unknown_data_does_not_claim_encryption(self):
        report = analyze_bytes(bytes(range(256)) * 10)
        self.assertEqual(report['magic_candidates'], [])
        self.assertNotIn('encrypted', report)

    def make_zip(self, entries):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            for name, data in entries:
                z.writestr(name, data)
        return buf.getvalue()

    def test_zip_is_read_in_memory_and_never_extracted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fw.zip'
            path.write_bytes(self.make_zip([('../outside.bin', b'example')]))
            with self.assertRaises(ValueError):
                read_image(path)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_ambiguous_zip_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fw.zip'
            path.write_bytes(self.make_zip([('a.bin', b'a'), ('b.bin', b'b')]))
            with self.assertRaises(ValueError):
                read_image(path)

    def test_expansion_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fw.zip'
            path.write_bytes(self.make_zip([('fw.bin', b'x' * 33)]))
            with self.assertRaises(ValueError):
                read_image(path, max_bytes=32)

    def test_single_image_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fw.zip'
            path.write_bytes(self.make_zip([('Release Note.pdf', b'pdf'), ('folder/fw.bin', b'payload')]))
            data, name = read_image(path)
            self.assertEqual((data, name), (b'payload', 'folder/fw.bin'))


if __name__ == '__main__':
    unittest.main()

import hashlib
from pathlib import Path
import shutil
import struct
import unittest

from tools.decode_cloud import mgf1, decode_pss, parse_public_blob, decrypt_aes


class CloudTests(unittest.TestCase):
    def encoded(self, msg_hash, salt, prefix=b''):
        h = hashlib.sha256(b'\0' * 8 + msg_hash + salt).digest()
        db = b'\0' * (223 - len(salt) - 1) + b'\x01' + salt
        if prefix:
            db = prefix + db[len(prefix):]
        masked = bytearray(a ^ b for a, b in zip(db, mgf1(h, 223)))
        masked[0] &= 0x7f
        return bytes(masked) + h + b'\xbc'

    def test_recovers_authenticated_salt(self):
        mh = hashlib.sha256(b'message').digest()
        salt = bytes(range(48))
        self.assertEqual(decode_pss(self.encoded(mh, salt), mh, 2047), salt)

    def test_tampered_message_and_encoding_are_rejected(self):
        mh = hashlib.sha256(b'message').digest()
        encoded = self.encoded(mh, bytes(range(48)))
        for bad, digest in [(encoded[:-1] + b'\0', mh),
                            (encoded, hashlib.sha256(b'tampered').digest()),
                            (self.encoded(mh, bytes(range(48)), b'\x02'), mh),
                            (encoded[:-10], mh)]:
            with self.assertRaises(ValueError):
                decode_pss(bad, digest, 2047)

    def test_public_blob_validates_type_and_extent(self):
        blob = b'\x06\x02\0\0' + struct.pack('<I', 0xa400) + b'RSA1' + struct.pack('<II', 2048, 65537) + b'\xff' * 256
        n, e = parse_public_blob(blob)
        self.assertEqual((n.bit_length(), e), (2048, 65537))
        for bad in [blob[:-1], b'\0' + blob[1:], blob[:8] + b'BAD!' + blob[12:]]:
            with self.assertRaises(ValueError):
                parse_public_blob(bad)

    @unittest.skipUnless(shutil.which('node'), 'Node.js required for AES backend')
    def test_nist_aes_cbc_vector(self):
        key = bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c')
        iv = bytes.fromhex('000102030405060708090a0b0c0d0e0f')
        ciphertext = bytes.fromhex('7649abac8119b246cee98e9b12e9197d')
        expected = bytes.fromhex('6bc1bee22e409f96e93d7e117393172a')
        self.assertEqual(decrypt_aes(ciphertext, key, iv, 'node'), expected)


if __name__ == '__main__':
    unittest.main()

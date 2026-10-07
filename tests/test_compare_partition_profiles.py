import subprocess
import unittest
import zlib

from tools.compare_partition_profiles import KEY_HEX, IV_HEX, decode_partition_blob, keyword_context


class PartitionProfileTests(unittest.TestCase):
    def test_keyword_context_is_bounded_and_deduplicated(self):
        text = 'prefix operation_mode=router,ap middle wireless_sta_config_5g=apclii0 suffix'
        rows = keyword_context(text, ('operation_mode', 'wireless_sta_config_5g'), radius=24)
        self.assertEqual(len(rows), 2)
        self.assertTrue(any('operation_mode=router,ap' in row for row in rows))
        self.assertTrue(any('wireless_sta_config_5g=apclii0' in row for row in rows))
        self.assertTrue(all(len(row) <= 49 for row in rows))

    def test_decode_matches_published_zlib_then_aes_format(self):
        plain = b'<profile operation_mode="router,ap"/>'
        compressed = zlib.compress(plain)
        encrypted = subprocess.run(
            ['openssl', 'aes-256-cbc', '-e', '-K', KEY_HEX, '-iv', IV_HEX],
            input=compressed, capture_output=True, check=True
        ).stdout
        self.assertEqual(decode_partition_blob(encrypted), plain)

    def test_missing_keyword_returns_empty_list(self):
        self.assertEqual(keyword_context('ordinary text', ('wireless_sta',)), [])


if __name__ == '__main__':
    unittest.main()

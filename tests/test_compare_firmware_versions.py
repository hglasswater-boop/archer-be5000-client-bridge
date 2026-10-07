import hashlib
import unittest

from tools.compare_firmware_versions import MARKERS, SELECTED_PATHS, compare_versions, summarize_bytes


class FirmwareVersionComparisonTests(unittest.TestCase):
    def test_summary_is_deterministic_and_counts_markers(self):
        data = b'apclii0 ApCliEnable reconnect reconnect disconnect'
        summary = summarize_bytes(data)
        self.assertEqual(summary['size'], len(data))
        self.assertEqual(summary['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(summary['markers']['apclii0'], 1)
        self.assertEqual(summary['markers']['ApCliEnable'], 1)
        self.assertEqual(summary['markers']['reconnect'], 2)
        self.assertEqual(summary['markers']['disconnect'], 1)
        for marker in MARKERS:
            self.assertIn(marker, summary['markers'])

    def test_compare_preserves_supplied_version_order(self):
        result = compare_versions({
            '1.0.2': {'/usr/bin/wifix': b'same'},
            '1.2.0': {'/usr/bin/wifix': b'same'},
        })
        self.assertEqual(result['versions'], ['1.0.2', '1.2.0'])
        row = result['files']['/usr/bin/wifix']
        self.assertTrue(row['byte_identical'])
        self.assertEqual(list(row['versions']), ['1.0.2', '1.2.0'])

    def test_changed_file_is_not_reported_identical(self):
        result = compare_versions({
            '1.0.2': {'/usr/bin/meshd': b'reconnect'},
            '1.2.0': {'/usr/bin/meshd': b'disconnect'},
        })
        self.assertFalse(result['files']['/usr/bin/meshd']['byte_identical'])

    def test_missing_file_is_explicit_and_prevents_identical_claim(self):
        result = compare_versions({
            '1.0.2': {'/usr/bin/wifix': b'present'},
            '1.2.0': {'/usr/bin/wifix': None},
        })
        row = result['files']['/usr/bin/wifix']
        self.assertFalse(row['byte_identical'])
        self.assertTrue(row['versions']['1.0.2']['present'])
        self.assertFalse(row['versions']['1.2.0']['present'])
        self.assertNotIn('sha256', row['versions']['1.2.0'])


    def test_daemon_gating_scripts_are_in_version_comparison(self):
        for path in ('/etc/init.d/meshd', '/etc/init.d/apsd', '/etc/init.d/tpbr'):
            self.assertIn(path, SELECTED_PATHS)


if __name__ == '__main__':
    unittest.main()

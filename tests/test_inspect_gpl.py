import io
import json
from pathlib import Path
import re
import tarfile
import tempfile
import unittest

from tools.inspect_gpl import scan_archive


class GPLTests(unittest.TestCase):
    def archive(self, path, entries):
        with tarfile.open(path, 'w:gz') as tar:
            for name, content, kind in entries:
                info = tarfile.TarInfo(name)
                if kind == 'link':
                    info.type = tarfile.SYMTYPE
                    info.linkname = '/etc/passwd'
                    tar.addfile(info)
                else:
                    info.size = len(content)
                    tar.addfile(info, io.BytesIO(content))

    def test_paths_are_data_and_links_are_never_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archive(root / 'a.tgz', [('../unsafe.config', b'CONFIG_A=y', 'file'), ('evil.config', b'', 'link')])
            result = scan_archive(root / 'a.tgz', root / 'out', re.compile('config'))
            self.assertEqual(len(result['selected']), 1)
            self.assertFalse((root / 'unsafe.config').exists())
            saved = root / 'out' / result['selected'][0]['saved_as']
            self.assertEqual(saved.read_bytes(), b'CONFIG_A=y')
            self.assertEqual(result['members'], 2)

    def test_individual_size_and_binary_skip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archive(root / 'a.tgz', [('big', b'x' * 40, 'file'), ('binary', b'a\0b', 'file')])
            result = scan_archive(root / 'a.tgz', root / 'out', re.compile('.'), member_limit=32)
            self.assertEqual(result['selected'], [])
            self.assertEqual(result['skipped_selected'], 2)

    def test_total_selected_limit_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archive(root / 'a.tgz', [('a', b'hello', 'file'), ('b', b'world', 'file')])
            with self.assertRaises(ValueError):
                scan_archive(root / 'a.tgz', root / 'out', re.compile('.'), selected_limit=8)
            self.assertFalse((root / 'out' / 'summary.json').exists())

    def test_archive_total_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archive(root / 'a.tgz', [('a', b'x' * 50, 'file')])
            with self.assertRaises(ValueError):
                scan_archive(root / 'a.tgz', root / 'out', re.compile('nomatch'), archive_limit=32)


if __name__ == '__main__':
    unittest.main()

import unittest

from tools.aarch64_string_xrefs import find_xrefs, map_file_offset


class Aarch64StringXrefTests(unittest.TestCase):
    def test_maps_file_offset_through_load_segment(self):
        segments = [
            {'offset': 0x1000, 'vaddr': 0x400000, 'filesz': 0x2000},
        ]
        self.assertEqual(map_file_offset(segments, 0x1123), 0x400123)
        self.assertIsNone(map_file_offset(segments, 0x5000))

    def test_resolves_adrp_add_reference(self):
        disasm = '''
  401000: 90000260 adrp x0, 440000 <x>
  401004: 91048c00 add x0, x0, #0x123
  401008: 94000001 bl 40100c
'''
        refs = find_xrefs(disasm, 0x440123)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['reference_address'], 0x401004)
        self.assertEqual(refs[0]['kind'], 'adrp+add')

    def test_ignores_different_register_or_address(self):
        disasm = '''
  401000: 90000260 adrp x0, 440000 <x>
  401004: 91048c21 add x1, x1, #0x123
  401008: 10000902 adr x2, 440120
'''
        self.assertEqual(find_xrefs(disasm, 0x440123), [])

    def test_resolves_direct_adr_reference(self):
        disasm = '''
  401000: 10000900 adr x0, 440123
  401004: d65f03c0 ret
'''
        refs = find_xrefs(disasm, 0x440123)
        self.assertEqual([(r['reference_address'], r['kind']) for r in refs], [(0x401000, 'adr')])


if __name__ == '__main__':
    unittest.main()

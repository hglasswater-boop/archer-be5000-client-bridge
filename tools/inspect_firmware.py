"""Offline inventory only. No extraction, execution, decryption or device access."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import zipfile

MAX_BYTES = 128 * 1024 * 1024
MAGICS = {
    b'hsqs': 'squashfs_le', b'\x7fELF': 'elf',
    b'\x27\x05\x19\x56': 'uimage', b'\xd0\x0d\xfe\xed': 'fdt_or_fit',
    b'UBI#': 'ubi', b'\x31\x18\x10\x06': 'ubifs',
    b'\x1f\x8b\x08': 'gzip', b'\xfd7zXZ\x00': 'xz',
}


def read_image(path, max_bytes=MAX_BYTES):
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError('input exceeds size limit')
    if not zipfile.is_zipfile(path):
        with path.open('rb') as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError('input exceeds size limit')
        return data, path.name
    with zipfile.ZipFile(path) as archive:
        entries = [i for i in archive.infolist() if not i.is_dir() and i.filename.lower().endswith('.bin')]
        if len(entries) != 1:
            raise ValueError('expected exactly one .bin member')
        entry = entries[0]
        name = PurePosixPath(entry.filename.replace('\\', '/'))
        if name.is_absolute() or '..' in name.parts or ':' in entry.filename:
            raise ValueError('unsafe archive member name')
        if entry.file_size > max_bytes:
            raise ValueError('expanded image exceeds size limit')
        with archive.open(entry) as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError('expanded image exceeds size limit')
        return data, entry.filename


def analyze_bytes(data):
    candidates = []
    for magic, kind in MAGICS.items():
        start = 0
        while True:
            offset = data.find(magic, start)
            if offset < 0:
                break
            start = offset + 1
            hit = {'kind': kind, 'offset': offset, 'offset_hex': hex(offset), 'status': 'candidate'}
            if kind == 'squashfs_le':
                if offset + 96 > len(data):
                    hit['status'] = 'truncated_header'
                else:
                    major, minor = struct.unpack_from('<HH', data, offset + 28)
                    used = struct.unpack_from('<Q', data, offset + 40)[0]
                    hit.update(version=[major, minor], bytes_used=used,
                               extent_in_bounds=(major == 4 and 96 <= used <= len(data) - offset))
            elif kind == 'fdt_or_fit':
                if offset + 40 > len(data):
                    hit['status'] = 'truncated_header'
                else:
                    total = struct.unpack_from('>I', data, offset + 4)[0]
                    hit.update(total_size=total, extent_in_bounds=40 <= total <= len(data) - offset)
            candidates.append(hit)
    header_strings = [{'offset': m.start(), 'text': m.group().decode('ascii')}
                      for m in re.finditer(rb'[\x20-\x7e]{8,}', data[:65536])]
    return {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'first_256_bytes_hex': data[:256].hex(),
            'magic_candidates': sorted(candidates, key=lambda x: x['offset']),
            'header_strings': header_strings,
            'warning': 'Magic hits are candidates, not verified filesystems, flash partitions or evidence of boot verification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output and args.output.resolve() == args.image.resolve():
        parser.error('output must not overwrite input')
    data, member = read_image(args.image)
    report = analyze_bytes(data)
    report['member'] = member
    report['archive_sha256'] = hashlib.sha256(args.image.read_bytes()).hexdigest()
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding='utf-8')
    else:
        print(rendered)


if __name__ == '__main__':
    main()

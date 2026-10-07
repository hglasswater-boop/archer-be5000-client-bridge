"""Decode public TP-Link partition profile/default-config files and summarize STA-relevant fields."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import zlib

KEY_HEX = '2EB38F7EC41D4B8E1422805BCD5F740BC3B95BE163E39D67579EB344427F7836'
IV_HEX = '360028C9064242F81074F4C127D299F6'
MAX_CONFIG = 2 * 1024 * 1024

PROFILE_KEYWORDS = (
    'operation_mode',
    'wireless_sta',
    'supportoperationmode',
    'wds',
    'repeater',
    'client',
    'hotspot',
)
DEFAULT_KEYWORDS = (
    'apcli0',
    'apclii0',
    'mode=sta',
    'mode="sta"',
    "mode='sta'",
    'mesh=on',
    'mesh=off',
    'mesh="on"',
    'mesh="off"',
    "mesh='on'",
    "mesh='off'",
)


def decode_partition_blob(blob, openssl='openssl'):
    if not isinstance(blob, bytes) or not blob or len(blob) > MAX_CONFIG:
        raise ValueError('invalid encrypted config extent')
    decrypted = subprocess.run(
        [openssl, 'aes-256-cbc', '-d', '-K', KEY_HEX, '-iv', IV_HEX],
        input=blob, capture_output=True, check=True
    ).stdout
    plain = zlib.decompress(decrypted)
    if not plain or len(plain) > MAX_CONFIG:
        raise ValueError('invalid decoded config extent')
    return plain


def keyword_context(text, keywords, radius=180):
    if not isinstance(text, str) or radius < 1:
        raise ValueError('invalid context input')
    lower = text.lower()
    rows = []
    seen = set()
    for keyword in keywords:
        needle = keyword.lower()
        start = 0
        while True:
            index = lower.find(needle, start)
            if index < 0:
                break
            left = max(0, index - radius)
            right = min(len(text), index + len(needle) + radius)
            snippet = re.sub(r'\s+', ' ', text[left:right]).strip()
            if snippet not in seen:
                seen.add(snippet)
                rows.append(snippet)
            start = index + len(needle)
    return rows


def read_public_configs(rootfs_path):
    try:
        from dissect.squashfs import SquashFS
    except ImportError as error:
        raise RuntimeError('dissect.squashfs is required') from error
    with Path(rootfs_path).open('rb') as source:
        fs = SquashFS(source)
        result = {}
        for name, path in (
            ('profile', '/etc/partition_config/profile'),
            ('default_config', '/etc/partition_config/default-config'),
        ):
            node = fs.get(path)
            if not node.is_file():
                raise ValueError(f'expected regular file: {path}')
            encrypted = node.open().read(MAX_CONFIG + 1)
            if len(encrypted) > MAX_CONFIG:
                raise ValueError(f'config exceeds size limit: {path}')
            result[name] = decode_partition_blob(encrypted).decode('utf-8', errors='replace')
        return result


def parse_rootfs(value):
    if '=' not in value:
        raise argparse.ArgumentTypeError('expected VERSION=PATH')
    version, path = value.split('=', 1)
    if not version or not path:
        raise argparse.ArgumentTypeError('expected non-empty VERSION=PATH')
    return version, Path(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', action='append', type=parse_rootfs, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'versions': {}}
    for version, path in args.rootfs:
        if version in report['versions']:
            parser.error(f'duplicate version: {version}')
        if not path.is_file():
            parser.error(f'rootfs not found: {path}')
        decoded = read_public_configs(path)
        report['versions'][version] = {
            'profile_context': keyword_context(decoded['profile'], PROFILE_KEYWORDS),
            'default_sta_context': keyword_context(decoded['default_config'], DEFAULT_KEYWORDS),
        }
    report['warning'] = (
        'Contexts come only from public firmware defaults/profile data. '
        'They do not establish live per-device state or successful association.'
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

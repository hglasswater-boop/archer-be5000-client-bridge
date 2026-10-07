"""Compare selected STA/APCLI-related files from decoded SquashFS rootfs images."""
import argparse
import hashlib
import json
from pathlib import Path

MARKERS = (
    'apclii0',
    'ApCliEnable',
    'wpa_cli',
    'reconnect',
    'disconnect',
    'MACRepeater',
    'tp_mesh_enable',
)
SELECTED_PATHS = (
    '/usr/bin/wifix',
    '/usr/bin/meshd',
    '/lib/wifi/wifix_profile.ini',
    '/etc/init.d/wifix',
    '/etc/meshd_cfg.json',
    '/etc/meshd_cfg_be260v1_jp.json',
)
MAX_SELECTED_FILE = 32 * 1024 * 1024


def summarize_bytes(data):
    if not isinstance(data, bytes):
        raise TypeError('file content must be bytes')
    return {
        'present': True,
        'size': len(data),
        'sha256': hashlib.sha256(data).hexdigest(),
        'markers': {marker: data.count(marker.encode('ascii')) for marker in MARKERS},
    }


def compare_versions(version_files):
    versions = list(version_files)
    paths = []
    for files in version_files.values():
        for path in files:
            if path not in paths:
                paths.append(path)
    result = {'versions': versions, 'files': {}}
    for path in paths:
        states = {}
        hashes = []
        all_present = True
        for version in versions:
            data = version_files[version].get(path)
            if data is None:
                states[version] = {'present': False}
                all_present = False
            else:
                states[version] = summarize_bytes(data)
                hashes.append(states[version]['sha256'])
        result['files'][path] = {
            'byte_identical': all_present and len(hashes) == len(versions) and len(set(hashes)) == 1,
            'versions': states,
        }
    return result


def read_selected_rootfs(image_path):
    try:
        from dissect.squashfs import SquashFS
    except ImportError as error:
        raise RuntimeError('dissect.squashfs is required for rootfs comparison') from error
    result = {}
    with Path(image_path).open('rb') as source:
        fs = SquashFS(source)
        for path in SELECTED_PATHS:
            try:
                node = fs.get(path)
            except Exception:
                result[path] = None
                continue
            if not node.is_file():
                result[path] = None
                continue
            stream = node.open()
            data = stream.read(MAX_SELECTED_FILE + 1)
            if len(data) > MAX_SELECTED_FILE:
                raise ValueError(f'selected file exceeds size limit: {path}')
            result[path] = data
    return result


def parse_rootfs_arg(value):
    if '=' not in value:
        raise argparse.ArgumentTypeError('expected VERSION=PATH')
    version, path = value.split('=', 1)
    if not version or not path:
        raise argparse.ArgumentTypeError('expected non-empty VERSION=PATH')
    return version, Path(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', action='append', required=True, type=parse_rootfs_arg,
                        help='decoded SquashFS volume as VERSION=PATH; repeat in release order')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    versions = {}
    for version, path in args.rootfs:
        if version in versions:
            parser.error(f'duplicate version: {version}')
        if not path.is_file():
            parser.error(f'rootfs not found: {path}')
        versions[version] = read_selected_rootfs(path)
    if len(versions) < 2:
        parser.error('at least two versions are required')
    report = compare_versions(versions)
    report['selected_paths'] = list(SELECTED_PATHS)
    report['warning'] = (
        'Marker presence and byte differences do not prove runtime reachability or working association.'
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({
        'versions': report['versions'],
        'changed_files': [path for path, row in report['files'].items() if not row['byte_identical']],
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()

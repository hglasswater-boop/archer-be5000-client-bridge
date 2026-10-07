"""Stream GPL archive metadata and bounded text candidates without path extraction."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile


def scan_archive(path, output, pattern, member_limit=2 * 1024**2,
                 selected_limit=64 * 1024**2, archive_limit=32 * 1024**3):
    path, output = Path(path), Path(output)
    # A fresh directory prevents stale successful reports after a failed run.
    output.mkdir(parents=True, exist_ok=False)
    selected, skipped, members, expanded, read_total = [], 0, 0, 0, 0
    with tarfile.open(path, 'r|gz') as archive, (output / 'members.jsonl').open('w', encoding='utf-8') as index:
        for member in archive:
            members += 1
            if member.size < 0:
                raise ValueError('negative member size')
            expanded += member.size
            if expanded > archive_limit:
                raise ValueError('archive declared payload exceeds limit')
            index.write(json.dumps({'name': member.name, 'size': member.size,
                                    'regular_file': member.isfile()}, ensure_ascii=True) + '\n')
            if not pattern.search(member.name) or not member.isfile():
                continue
            if member.size > member_limit:
                skipped += 1
                continue
            if read_total + member.size > selected_limit:
                raise ValueError('selected payload exceeds limit')
            with archive.extractfile(member) as stream:
                data = stream.read(member_limit + 1)
            if len(data) != member.size or len(data) > member_limit:
                raise ValueError('member length mismatch')
            read_total += len(data)
            if b'\0' in data:
                skipped += 1
                continue
            digest = hashlib.sha256(data).hexdigest()
            saved = digest + '.txt'
            (output / saved).write_bytes(data)
            selected.append({'name': member.name, 'size': len(data),
                             'sha256': digest, 'saved_as': saved})
    summary = {'members': members, 'declared_payload_bytes': expanded,
               'selected_read_bytes': read_total, 'skipped_selected': skipped,
               'selected': selected}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary



def scan_content(path, needle, member_limit=2 * 1024**2, match_limit=64, context_bytes=240):
    """Stream regular text members and return bounded contexts containing an exact byte token."""
    if not isinstance(needle, bytes) or not needle or len(needle) > 256:
        raise ValueError('needle must be 1..256 bytes')
    matches = []
    with tarfile.open(Path(path), 'r|gz') as archive:
        for member in archive:
            if not member.isfile() or member.size < 0 or member.size > member_limit:
                continue
            with archive.extractfile(member) as stream:
                data = stream.read(member_limit + 1)
            if len(data) != member.size or len(data) > member_limit or b'\0' in data:
                continue
            pos = data.find(needle)
            if pos < 0:
                continue
            if len(matches) >= match_limit:
                raise ValueError('content match count exceeds limit')
            start = max(0, pos - context_bytes)
            end = min(len(data), pos + len(needle) + context_bytes)
            context = data[start:end].decode('utf-8', errors='replace')
            matches.append({'name': member.name, 'size': member.size, 'offset': pos, 'context': context})
    return matches

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='new directory')
    parser.add_argument('--select', required=True, help='regex of archive member names')
    args = parser.parse_args()
    summary = scan_archive(args.archive, args.output, re.compile(args.select, re.I))
    print(json.dumps({k: v for k, v in summary.items() if k != 'selected'}))
    print('selected text candidates:', len(summary['selected']))


if __name__ == '__main__':
    main()

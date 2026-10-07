"""Find bounded AArch64 code references to selected strings in an ELF binary."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

PT_LOAD = 1
MAX_BINARY = 32 * 1024 * 1024
LINE = re.compile(r'^\s*([0-9a-fA-F]+):\s+(?:[0-9a-fA-F]{8}\s+)?([A-Za-z0-9_.]+)\s*(.*?)\s*$')
REG_IMM = re.compile(r'^(x\d+|w\d+),\s*(?:#)?(0x[0-9a-fA-F]+|[0-9a-fA-F]+)(?:\s+<.*>)?$')
ADD = re.compile(r'^(x\d+|w\d+),\s*(x\d+|w\d+),\s*#?(0x[0-9a-fA-F]+|[0-9]+)')


def parse_elf_load_segments(data):
    if len(data) < 64 or data[:4] != b'\x7fELF' or data[4] != 2 or data[5] != 1:
        raise ValueError('expected ELF64 little-endian image')
    machine = struct.unpack_from('<H', data, 18)[0]
    if machine != 183:
        raise ValueError('expected AArch64 ELF')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phentsize = struct.unpack_from('<H', data, 54)[0]
    phnum = struct.unpack_from('<H', data, 56)[0]
    if phentsize < 56 or phoff + phentsize * phnum > len(data):
        raise ValueError('invalid program header table')
    segments = []
    for index in range(phnum):
        off = phoff + index * phentsize
        p_type, _flags, p_offset, p_vaddr, _paddr, p_filesz, _memsz, _align = struct.unpack_from('<IIQQQQQQ', data, off)
        if p_type == PT_LOAD and p_filesz:
            if p_offset + p_filesz > len(data):
                raise ValueError('PT_LOAD exceeds file')
            segments.append({'offset': p_offset, 'vaddr': p_vaddr, 'filesz': p_filesz})
    if not segments:
        raise ValueError('no PT_LOAD segments')
    return segments


def map_file_offset(segments, offset):
    for segment in segments:
        start = segment['offset']
        end = start + segment['filesz']
        if start <= offset < end:
            return segment['vaddr'] + (offset - start)
    return None


def _hex_value(value):
    if value.lower().startswith('0x'):
        return int(value, 16)
    return int(value, 16)


def _decimal_or_hex_imm(value):
    if value.lower().startswith('0x'):
        return int(value, 16)
    return int(value, 10)


def parse_disassembly(text):
    instructions = []
    for raw in text.splitlines():
        match = LINE.match(raw)
        if not match:
            continue
        instructions.append({
            'address': int(match.group(1), 16),
            'mnemonic': match.group(2).lower(),
            'operands': match.group(3),
            'raw': raw.rstrip(),
        })
    return instructions


def find_xrefs(disassembly, target_va, context=8):
    instructions = parse_disassembly(disassembly)
    refs = []
    for index, insn in enumerate(instructions):
        if insn['mnemonic'] == 'adr':
            match = REG_IMM.match(insn['operands'])
            if match and _hex_value(match.group(2)) == target_va:
                refs.append({
                    'reference_address': insn['address'],
                    'kind': 'adr',
                    'context': [x['raw'] for x in instructions[max(0, index-context):index+context+1]],
                })
        if insn['mnemonic'] != 'adrp':
            continue
        match = REG_IMM.match(insn['operands'])
        if not match:
            continue
        register, page_text = match.groups()
        page = _hex_value(page_text)
        for next_index in range(index + 1, min(index + 6, len(instructions))):
            nxt = instructions[next_index]
            add = ADD.match(nxt['operands']) if nxt['mnemonic'] == 'add' else None
            if not add:
                continue
            dst, src, imm_text = add.groups()
            if dst != register or src != register:
                continue
            effective = page + _decimal_or_hex_imm(imm_text)
            if effective == target_va:
                refs.append({
                    'reference_address': nxt['address'],
                    'kind': 'adrp+add',
                    'adrp_address': insn['address'],
                    'context': [x['raw'] for x in instructions[max(0, index-context):next_index+context+1]],
                })
            break
    return refs


def marker_occurrences(data, marker):
    needle = marker.encode('utf-8')
    if not needle:
        raise ValueError('marker must not be empty')
    result = []
    start = 0
    while True:
        offset = data.find(needle, start)
        if offset < 0:
            break
        result.append(offset)
        start = offset + 1
    return result


def analyze(binary, markers, objdump):
    binary = Path(binary)
    if binary.stat().st_size > MAX_BINARY:
        raise ValueError('binary exceeds size limit')
    data = binary.read_bytes()
    segments = parse_elf_load_segments(data)
    completed = subprocess.run([objdump, '-d', str(binary)], capture_output=True, text=True, check=True)
    report = {'binary': binary.name, 'size': len(data), 'markers': {}}
    for marker in markers:
        occurrences = []
        for offset in marker_occurrences(data, marker):
            va = map_file_offset(segments, offset)
            item = {'file_offset': offset, 'virtual_address': va, 'xrefs': []}
            if va is not None:
                item['xrefs'] = find_xrefs(completed.stdout, va)
            occurrences.append(item)
        report['markers'][marker] = occurrences
    report['limitations'] = [
        'Only direct ADR and ADRP+ADD string references are resolved.',
        'Zero XREFs do not prove the string is unreachable; GOT/table/indirect references are not resolved.',
        'Context windows are not claimed function boundaries.',
    ]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('--marker', action='append', required=True)
    parser.add_argument('--objdump', default='aarch64-linux-gnu-objdump')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.binary, args.marker, args.objdump)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({
        marker: sum(len(item['xrefs']) for item in occurrences)
        for marker, occurrences in report['markers'].items()
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()

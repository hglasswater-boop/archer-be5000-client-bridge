"""Read static UBI volumes from a single pristine package, validating CRCs. No flashing."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib


def crc_ok(data, expected):
    return (~zlib.crc32(data) & 0xffffffff) == expected


def read_static_volumes(image, start, peb_size):
    if start < 0 or peb_size < 128 or start >= len(image) or (len(image)-start) % peb_size:
        raise ValueError('invalid UBI extent')
    sequence = None
    volumes = {}
    for offset in range(start, len(image), peb_size):
        block = image[offset:offset+peb_size]
        ec = block[:64]
        if ec[:5] != b'UBI#\x01' or not crc_ok(ec[:60], struct.unpack_from('>I',ec,60)[0]):
            raise ValueError('invalid EC header / CRC')
        vid_offset, data_offset, seq = struct.unpack_from('>III',ec,16)
        if not 64 <= vid_offset <= data_offset-64 or not data_offset < peb_size:
            raise ValueError('invalid UBI header offsets')
        if sequence is not None and seq != sequence:
            raise ValueError('mixed UBI image sequences')
        sequence = seq
        vid = block[vid_offset:vid_offset+64]
        if vid == b'\xff'*64 and block[vid_offset:] == b'\xff'*(peb_size-vid_offset):
            continue  # pristine erased reserve PEB with valid EC header
        if vid[:5] != b'UBI!\x01' or not crc_ok(vid[:60], struct.unpack_from('>I',vid,60)[0]):
            raise ValueError('invalid VID header / CRC')
        vol_id, lnum = struct.unpack_from('>II',vid,8)
        if vol_id == 0x7fffefff:
            continue  # layout volume: no filesystem payload
        size, used, pad, checksum = struct.unpack_from('>IIII',vid,20)
        if vid[5] != 2 or vid[6] != 0 or used < 1 or lnum >= used or size < 1 or size > peb_size-data_offset-pad:
            raise ValueError('unsupported / invalid static volume')
        payload = block[data_offset:data_offset+size]
        if not crc_ok(payload, checksum):
            raise ValueError('static volume data CRC mismatch')
        expected, chunks = volumes.setdefault(vol_id,(used,{}))
        if expected != used or lnum in chunks:
            raise ValueError('inconsistent or duplicate logical blocks')
        chunks[lnum] = payload
    result = {}
    for vol_id,(used,chunks) in volumes.items():
        if len(chunks) != used:
            raise ValueError('missing logical block')
        result[vol_id] = b''.join(chunks[n] for n in range(used))
    if not result:
        raise ValueError('no static volumes found')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path)
    parser.add_argument('--start',type=lambda s:int(s,0),required=True)
    parser.add_argument('--peb-size',type=lambda s:int(s,0),required=True)
    parser.add_argument('--output',type=Path,required=True,help='new analysis directory')
    args = parser.parse_args()
    if args.image.stat().st_size > 128*1024*1024 or args.output.exists():
        parser.error('input too large or output already exists')
    volumes = read_static_volumes(args.image.read_bytes(),args.start,args.peb_size)
    args.output.mkdir(parents=True)
    summary = {'start':args.start,'peb_size':args.peb_size,'ec_vid_static_data_crc_verified':True,'volumes':[]}
    for vid,data in sorted(volumes.items()):
        (args.output / f'volume-{vid}.bin').write_bytes(data)
        summary['volumes'].append({'id':vid,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'first16_hex':data[:16].hex()})
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()

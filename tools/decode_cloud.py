"""Authenticate and decode a COPY of TP-Link cloud firmware using its GPL public key."""
import argparse
import base64
import hashlib
import hmac
import json
from pathlib import Path
import re
import struct
import subprocess

from tools.inspect_firmware import read_image, analyze_bytes


def mgf1(seed, length):
    return b''.join(hashlib.sha256(seed + struct.pack('>I', counter)).digest()
                    for counter in range((length + 31) // 32))[:length]


def decode_pss(encoded, msg_hash, em_bits):
    em_len = (em_bits + 7) // 8
    if len(encoded) != em_len or em_len < 34 or encoded[-1] != 0xbc or len(msg_hash) != 32:
        raise ValueError('invalid PSS extent or trailer')
    h = encoded[-33:-1]
    masked = encoded[:-33]
    unused = 8 * em_len - em_bits
    if not 0 <= unused <= 7 or masked[0] >> (8 - unused):
        raise ValueError('invalid PSS leading bits')
    db = bytearray(a ^ b for a, b in zip(masked, mgf1(h, len(masked))))
    db[0] &= 0xff >> unused
    marker = 0
    while marker < len(db) and db[marker] == 0:
        marker += 1
    if marker == len(db) or db[marker] != 1:
        raise ValueError('invalid PSS padding')
    salt = bytes(db[marker + 1:])
    expected = hashlib.sha256(b'\0' * 8 + msg_hash + salt).digest()
    if not hmac.compare_digest(expected, h):
        raise ValueError('PSS authentication failed')
    return salt


def parse_public_blob(blob):
    if len(blob) < 20 or blob[:4] != b'\x06\x02\0\0' or blob[8:12] != b'RSA1':
        raise ValueError('invalid PUBLICKEYBLOB header')
    bits, exponent = struct.unpack_from('<II', blob, 12)
    if bits != 2048 or len(blob) != 20 + bits // 8 or exponent < 3 or exponent % 2 == 0:
        raise ValueError('unsupported public key extent')
    modulus = int.from_bytes(blob[20:], 'little')
    if modulus.bit_length() != bits or modulus % 2 == 0:
        raise ValueError('invalid RSA modulus')
    return modulus, exponent


def decrypt_aes(ciphertext, key, iv, node):
    if len(key) != 16 or len(iv) != 16 or len(ciphertext) % 16:
        raise ValueError('invalid AES-CBC extent')
    result = subprocess.run([node, str(Path(__file__).with_name('aes_cbc_decrypt.cjs'))],
                            input=key + iv + ciphertext, capture_output=True, check=True)
    if len(result.stdout) != len(ciphertext):
        raise ValueError('AES backend returned unexpected length')
    return result.stdout


def decode_image(image, public_blob, node):
    if len(image) < 0x268 or image[20:34] != b'fw-type:Cloud\n' or image[0x112] != 2:
        raise ValueError('not supported RSA2048 cloud image')
    if struct.unpack_from('>I', image)[0] != len(image):
        raise ValueError('image size header mismatch')
    n, e = parse_public_blob(public_blob)
    signature = int.from_bytes(image[0x130:0x230], 'little')
    if signature >= n:
        raise ValueError('RSA signature out of range')
    signed = bytearray(image[20:])
    signed[0x130 - 20:0x230 - 20] = b'\0' * 256
    encoded = pow(signature, e, n).to_bytes(256, 'big')
    salt = decode_pss(encoded, hashlib.sha256(signed).digest(), n.bit_length() - 1)
    if len(salt) <= 32:
        raise ValueError('authenticated salt does not select encrypted payload')
    plain_magic = bytes.fromhex('aa559dd1a8c88331c969fbbfbcf0d43270c755aa')
    if image[0x254:0x268] == plain_magic:
        raise ValueError('payload is already plaintext; no decoding needed')
    end = 0x230 + ((len(image) - 0x230) // 16) * 16
    payload = decrypt_aes(image[0x230:end], salt[:16], salt[16:32], node)
    decoded = image[:0x230] + payload + image[end:]
    if decoded[0x254:0x268] != plain_magic:
        raise ValueError('decoded vendor marker mismatch')
    return decoded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--nm-source', type=Path, required=True, help='GPL nm_fwup.c containing public key')
    parser.add_argument('--output', type=Path, required=True, help='new local analysis .bin, never flash it')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--node', default='node')
    args = parser.parse_args()
    outputs = [args.output.resolve(), args.report.resolve()]
    inputs = [args.image.resolve(), args.nm_source.resolve()]
    if len(set(outputs)) != 2 or any(p in inputs or p.exists() for p in outputs):
        parser.error('outputs must be distinct new files and cannot overwrite inputs')
    if args.nm_source.stat().st_size > 128 * 1024:
        parser.error('source exceeds size limit')
    source = args.nm_source.read_bytes()
    match = re.search(rb'l_rsa2048PubKey\[\]\s*=\s*(.*?);', source, re.S)
    if not match:
        parser.error('GPL RSA2048 public key declaration missing')
    blob = base64.b64decode(b''.join(re.findall(rb'"([^\"]*)"', match.group(1))), validate=True)
    original, member = read_image(args.image)
    decoded = decode_image(original, blob, args.node)
    report = analyze_bytes(decoded)
    report.update(original_sha256=hashlib.sha256(original).hexdigest(), member=member,
                  nm_source_sha256=hashlib.sha256(source).hexdigest(),
                  rsa_pss_sha256_verified=True, aes_cbc_payload_decoded=True,
                  warning='Decoded analysis COPY retains an invalid signature for its changed payload. NEVER flash it.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(decoded)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['original_sha256', 'sha256', 'rsa_pss_sha256_verified', 'aes_cbc_payload_decoded']}))


if __name__ == '__main__':
    main()

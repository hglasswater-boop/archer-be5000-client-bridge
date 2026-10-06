// Local crypto only. Input and output are captured pipes, never command arguments.
const crypto = require('node:crypto');
let input = '';
process.stdin.on('data', chunk => {
  input += chunk;
  if (Buffer.byteLength(input) > 256 * 1024) process.exit(1);
});
process.stdin.on('end', () => {
  try {
    const j = JSON.parse(input);
    if (typeof j.data !== 'string' || j.data.length > 128 * 1024) throw Error();
    let result;
    if (j.operation === 'aes-encrypt' || j.operation === 'aes-decrypt') {
      if (!/^[0-9a-f]{32}$/i.test(j.key) || !/^[0-9a-f]{32}$/i.test(j.iv)) throw Error();
      const key = Buffer.from(j.key, 'hex'), iv = Buffer.from(j.iv, 'hex');
      if (j.operation === 'aes-encrypt') {
        const cipher = crypto.createCipheriv('aes-128-cbc', key, iv);
        const data = Buffer.from(j.data, j.inputHex ? 'hex' : 'utf8');
        result = Buffer.concat([cipher.update(data), cipher.final()]).toString('base64');
      } else {
        if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(j.data)) throw Error();
        const data = Buffer.from(j.data, 'base64');
        if (!data.length || data.length % 16) throw Error();
        const cipher = crypto.createDecipheriv('aes-128-cbc', key, iv);
        result = new TextDecoder('utf-8', { fatal: true }).decode(
          Buffer.concat([cipher.update(data), cipher.final()]));
      }
    } else if (j.operation === 'rsa-v15' || j.operation === 'rsa-oaep') {
      if (!/^[0-9a-f]{512}$/i.test(j.n) || !/^[0-9a-f]{1,8}$/i.test(j.e)) throw Error();
      const e = j.e.length % 2 ? '0' + j.e : j.e;
      const publicKey = crypto.createPublicKey({format: 'jwk', key: {
        kty: 'RSA', n: Buffer.from(j.n, 'hex').toString('base64url'),
        e: Buffer.from(e, 'hex').toString('base64url'),
      }});
      const padding = j.operation === 'rsa-v15' ? crypto.constants.RSA_PKCS1_PADDING
        : crypto.constants.RSA_PKCS1_OAEP_PADDING;
      result = crypto.publicEncrypt({key: publicKey, padding, oaepHash: 'sha1'},
        Buffer.from(j.data, 'utf8')).toString('hex');
    } else throw Error();
    process.stdout.write(JSON.stringify({result}));
  } catch {
    // Never echo input, exception objects, key material or plaintext.
    process.stderr.write('Crypto operation failed\n');
    process.exitCode = 1;
  }
});

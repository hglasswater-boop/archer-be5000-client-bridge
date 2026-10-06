// Offline AES backend. stdin: 16-byte key, 16-byte IV, then ciphertext.
const { createDecipheriv } = require('node:crypto');
const chunks = [];
let length = 0;
process.stdin.on('data', chunk => {
  length += chunk.length;
  if (length > 128 * 1024 * 1024 + 32) {
    process.stderr.write('Input exceeds limit\n');
    process.exit(1);
  }
  chunks.push(chunk);
});
process.stdin.on('end', () => {
  const input = Buffer.concat(chunks);
  if (input.length < 32 || (input.length - 32) % 16 !== 0) {
    process.stderr.write('Invalid CBC input length\n');
    process.exit(1);
  }
  const decipher = createDecipheriv('aes-128-cbc', input.subarray(0, 16), input.subarray(16, 32));
  decipher.setAutoPadding(false);
  process.stdout.write(Buffer.concat([decipher.update(input.subarray(32)), decipher.final()]));
});

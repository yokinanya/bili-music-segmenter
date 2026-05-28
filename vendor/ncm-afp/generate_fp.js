const fs = require('fs');
const { GenerateFP } = require('./afp.js');

async function main() {
  const input = process.argv[2];
  if (!input) {
    throw new Error('usage: node generate_fp.js pcm_f32le_file');
  }
  const buffer = fs.readFileSync(input);
  const samples = new Float32Array(
    buffer.buffer,
    buffer.byteOffset,
    Math.floor(buffer.byteLength / Float32Array.BYTES_PER_ELEMENT),
  );
  const fp = await GenerateFP(samples);
  process.stdout.write(fp);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

// Adapted from NeteaseCloudMusicApi 4.32.0 module/audio_match.js (MIT).
// Copyright (c) 2013-2022 Binaryify. See LICENSE.
// Built-in Node fetch replaces axios; credentials are received on stdin.
const { randomUUID } = require('node:crypto');
const MATCH_URL = 'https://interface.music.163.com/api/music/audio/match';
async function audioMatch({ audioFP, duration, cookie = '', timeout }) {
  if (typeof audioFP !== 'string' || !audioFP || !Number.isFinite(duration) || duration <= 0) {
    throw new Error('Invalid fingerprint or duration');
  }
  const url = new URL(MATCH_URL);
  url.search = new URLSearchParams({ sessionId: randomUUID().replaceAll('-', ''), algorithmCode: 'shazam_v2', duration: String(duration), rawdata: audioFP, times: '1', decrypt: '1' });
  const response = await fetch(url, { headers: cookie ? { Cookie: cookie } : {}, signal: AbortSignal.timeout(timeout * 1000) });
  if (!response.ok) throw new Error(`NetEase audio match HTTP ${response.status}`);
  const payload = await response.json();
  if (payload.code !== 200 || !payload.data) throw new Error(`Invalid NetEase response: ${JSON.stringify(payload)}`);
  return { code: payload.code, data: payload.data };
}
module.exports = { audioMatch };
if (require.main === module) {
  let input = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => { input += chunk; });
  process.stdin.on('end', () => audioMatch(JSON.parse(input)).then(value => process.stdout.write(JSON.stringify(value))).catch(error => { console.error(error.message); process.exitCode = 1; }));
}

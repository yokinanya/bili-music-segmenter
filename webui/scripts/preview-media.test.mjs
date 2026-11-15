import assert from 'node:assert/strict';
import test from 'node:test';
import { attachPreview, previewType } from '../src/lib/previewMedia.ts';

function fixture() {
  const listeners = new Map(), calls = [], errors = [];
  const video = { src: '', ownerDocument: { baseURI: 'http://127.0.0.1:7860/' }, pause: () => calls.push('pause'),
    removeAttribute: name => { assert.equal(name, 'src'); video.src = ''; },
    load: () => calls.push('load') };
  const player = {
    on: (event, callback) => listeners.set(event, callback),
    attachMediaElement: element => { assert.equal(element, video); calls.push('attach'); },
    load: () => calls.push('load-flv'), unload: () => calls.push('unload'),
    detachMediaElement: () => calls.push('detach'), destroy: () => calls.push('destroy'),
  };
  const library = { isSupported: () => true, Events: { ERROR: 'error', MEDIA_INFO: 'info' },
    createPlayer: (source, config) => {
      assert.equal(source.url, 'http://127.0.0.1:7860/source?token=test');
      assert.equal(source.type, 'flv');
      assert.equal(source.isLive, false);
      assert.equal(source.duration, 7_200_000);
      assert.equal(config.accurateSeek, true);
      assert.equal(config.seekType, 'range');
      assert.equal(config.autoCleanupSourceBuffer, true);
      return player;
    } };
  const options = { video, src: '/source?token=test', type: 'flv', duration: 7200,
    onError: message => errors.push(message) };
  return { options, library, calls, errors, listeners, player, video };
}

test('indexed FLV passes an absolute URL to the Blob worker and releases the previous player', () => {
  const f = fixture();
  const dispose = attachPreview(f.options, f.library);
  assert.deepEqual(f.calls, ['attach', 'load-flv']);
  f.listeners.get('info')({ hasKeyframesIndex: true });
  assert.deepEqual(f.errors, []);
  dispose();
  assert.deepEqual(f.calls.slice(2), ['unload', 'detach', 'destroy']);
});

test('native media uses the original URL and releases its connection', () => {
  const f = fixture();
  const dispose = attachPreview({ ...f.options, type: 'native' });
  assert.equal(f.video.src, '/source?token=test');
  dispose();
  assert.equal(f.video.src, '');
  assert.deepEqual(f.calls, ['pause', 'load']);
  assert.equal(previewType('Live.FLV'), 'flv');
  assert.equal(previewType('clip.mp4'), 'native');
});

test('missing FLV seek index and decoder errors are visible and stop loading', () => {
  const f = fixture();
  const dispose = attachPreview(f.options, f.library);
  f.listeners.get('info')({ hasKeyframesIndex: false });
  assert.match(f.errors[0], /关键帧索引/);
  assert.ok(f.calls.includes('unload'));
  dispose();
  const g = fixture();
  attachPreview(g.options, g.library);
  g.listeners.get('error')('MediaError', 'CodecUnsupported', { msg: 'HEVC unavailable' });
  assert.match(g.errors[0], /CodecUnsupported.*HEVC unavailable/);
  assert.ok(g.calls.includes('unload'));
});

test('unsupported MSE and failed initialization do not leave a running player', () => {
  const f = fixture();
  assert.throws(() => attachPreview(f.options, { ...f.library, isSupported: () => false }), /浏览器/);
  f.player.load = () => { throw new Error('initialization failed'); };
  assert.throws(() => attachPreview(f.options, f.library), /initialization failed/);
  assert.deepEqual(f.calls, ['attach', 'unload', 'detach', 'destroy']);
});

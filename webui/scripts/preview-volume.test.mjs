import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const { transformSync } = createRequire(import.meta.url)('next/dist/build/swc');
const { code } = transformSync(readFileSync(new URL('../src/components/PreviewVolume.tsx', import.meta.url), 'utf8'), {
  jsc: { parser: { syntax: 'typescript', tsx: true }, transform: { react: { runtime: 'automatic' } } },
  module: { type: 'commonjs' },
});

function preview(storage) {
  const refs = [], states = [];
  let ref = 0, state = 0, effect, deps, cleanup;
  const react = {
    useRef: initial => refs[ref++] ?? (refs[ref - 1] = { current: initial }),
    useState: initial => {
      const index = state++;
      return [states[index] ?? (states[index] = initial), value => { states[index] = value; }];
    },
    useEffect: (run, next) => {
      if (!deps || next.some((value, index) => value !== deps[index])) effect = () => {
        cleanup?.(); cleanup = run(); deps = next;
      };
    },
  };
  const jsx = (type, props) => ({ type, props });
  const exports = {};
  const localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
  runInNewContext(code, { exports, window: { localStorage }, require: name => ({
    react, 'react/jsx-runtime': { jsx, jsxs: jsx }, './Icon': { Icon: 'icon' },
    './Material': { IconButton: 'button', Slider: 'slider' },
  })[name] });
  const video = { current: null };
  const render = () => {
    ref = state = 0;
    return exports.PreviewVolume({ video, disabled: video.current === null }).props.children;
  };
  const attach = (element = Object.assign(new EventTarget(), { volume: 1, muted: false })) => {
    video.current = element;
    render(); effect?.(); effect = undefined;
    return element;
  };
  const change = callback => { callback(); video.current.dispatchEvent(new Event('volumechange')); };
  return {
    attach,
    setVolume: value => change(() => render()[1].props.onChange(value)),
    toggleMute: () => change(() => render()[0].props.onClick()),
    percent: () => render()[1].props.value,
  };
}

test('restores preview volume when media attaches after a reload', () => {
  const storage = new Map();
  const first = preview(storage);
  first.attach();
  first.setVolume(35);

  const reopened = preview(storage);
  reopened.attach(null);
  assert.equal(reopened.attach().volume, 0.35);
  assert.equal(reopened.percent(), 35);
});

test('restores mute and the last audible level after reopening at zero volume', () => {
  const storage = new Map();
  const first = preview(storage);
  first.attach();
  first.setVolume(42);
  first.toggleMute();

  const reopened = preview(storage);
  const video = reopened.attach();
  assert.equal(video.muted, true);
  reopened.toggleMute();
  assert.equal(reopened.percent(), 42);
  reopened.setVolume(0);

  const reopenedAtZero = preview(storage);
  reopenedAtZero.attach();
  assert.equal(reopenedAtZero.percent(), 0);
  reopenedAtZero.toggleMute();
  assert.equal(reopenedAtZero.percent(), 42);
});

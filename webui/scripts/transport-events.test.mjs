import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { runInNewContext } from 'node:vm';
import * as playback from '../src/lib/playback.ts';
import { icons } from '../src/lib/iconGeometries.ts';

const require = createRequire(import.meta.url);
const { transformSync } = require('next/dist/build/swc');

function loadComponent(name, load) {
  const module = { exports: {} };
  const source = readFileSync(new URL(`../src/components/${name}.tsx`, import.meta.url), 'utf8');
  const { code } = transformSync(source, {
    jsc: { parser: { syntax: 'typescript', tsx: true }, transform: { react: { runtime: 'automatic' } } },
    module: { type: 'commonjs' },
  });
  runInNewContext(code, { exports: module.exports, module, require: load });
  return module.exports;
}

function renderTransport(options = {}) {
  const queued = [], slots = [], effects = [];
  const media = Object.assign(new EventTarget(), { volume: 1, muted: false });
  let index = 0;
  const react = {
    useRef: value => ({ current: value }),
    useEffect: effect => effects.push(effect),
    useCallback: callback => callback,
    useState: initial => {
      const slot = index++;
      slots[slot] = typeof initial === 'function' ? initial() : initial;
      return [slots[slot], update => queued.push(() => {
        slots[slot] = typeof update === 'function' ? update(slots[slot]) : update;
      })];
    },
  };
  const jsx = (type, props) => {
    if (typeof type === 'function') return type(props);
    if (type === 'video') props.ref?.(media);
    return { type, props };
  };
  const load = name => {
    if (name === 'react') return react;
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'fragment' };
    if (name === '@/lib/playback') return playback;
    if (name === '@/lib/usePreviewSource') return { usePreviewSource: () => {} };
    if (name === '@/lib/iconGeometries') return { icons };
    if (name === './Material') return { Button: props => ({type:'button',props}), IconButton: props => ({type:'button',props:{...props,'aria-label':props.label}}),
      Slider: props => ({type:'input',props:{...props,'aria-label':props.label,onChange:event=>props.onChange(Number(event.currentTarget.value))}}) };
    if (name === './PreviewVolume' || name === './Icon') return loadComponent(name.slice(2), load);
    if (name === '@/lib/usePointerSeek') {
      const hook = { exports: {} };
      const source = readFileSync(new URL('../src/lib/usePointerSeek.ts', import.meta.url), 'utf8');
      const { code } = transformSync(source, { jsc: { parser: { syntax: 'typescript' } }, module: { type: 'commonjs' } });
      runInNewContext(code, { exports: hook.exports, module: hook, require: load });
      return hook.exports;
    }
    if (name === '@/lib/format') return { mediaTime: String };
    throw new Error(`Unexpected import: ${name}`);
  };
  const tree = loadComponent('PreviewTransport', load).PreviewTransport({ src: '/preview', onTime: () => {}, onError: () => {}, registerVideo: () => {}, ...options });
  const find = (node, predicate) => {
    if (!node || typeof node !== 'object') return null;
    if (predicate(node)) return node;
    return [node.props?.children].flat(Infinity).map(child => find(child, predicate)).find(Boolean);
  };
  effects.forEach(effect => effect());
  return { media, find: predicate => find(tree, predicate), video: find(tree, node => node.type === 'video'),
    flush: () => queued.forEach(update => update()), state: () => slots[0], audio: () => slots[2] };
}

test('metadata duration is captured before React clears the event currentTarget', () => {
  const transport = renderTransport();
  const event = { currentTarget: { duration: 5855 } };
  transport.video.props.onLoadedMetadata(event);
  event.currentTarget = null;
  transport.flush();
  assert.equal(transport.state().duration, 5855);
});

test('playing a selected clip stops exactly at its end and reports that position', () => {
  const times = [];
  const transport = renderTransport({ stopAt: 30, onTime: value => times.push(value) });
  let pauses = 0;
  Object.assign(transport.media, { paused: false, seeking: false, currentTime: 30.2, pause: () => { pauses++; transport.media.paused = true; } });
  transport.video.props.onTimeUpdate({ currentTarget: transport.media });
  assert.equal(pauses, 1);
  assert.equal(transport.media.currentTime, 30);
  assert.deepEqual(times, [30]);
});

test('paused seeking past a clip end stays unrestricted and whole-video playback is unchanged', () => {
  for (const options of [{ stopAt: 30, paused: true }, { paused: false }]) {
    const transport = renderTransport(options);
    Object.assign(transport.media, { paused: options.paused, currentTime: 40, pause: () => assert.fail('unexpected pause') });
    transport.video.props.onTimeUpdate({ currentTarget: transport.media });
    assert.equal(transport.media.currentTime, 40);
  }
});

test('preview volume slider changes media volume and unmutes it', () => {
  const transport = renderTransport();
  const slider = transport.find(node => node.type === 'input' && node.props['aria-label'] === '播放音量');
  assert.ok(slider, 'preview must provide a volume slider');
  transport.media.muted = true;
  slider.props.onChange({ currentTarget: { value: '35' } });
  assert.equal(transport.media.volume, 0.35);
  assert.equal(transport.media.muted, false);
  transport.flush();
  assert.equal(transport.audio().volume, 0.35, 'slider updates immediately without waiting for volumechange');
});

test('scrolling over the volume control changes volume without scrolling the page', () => {
  const transport = renderTransport();
  const volume = transport.find(node => node.type === 'div' && node.props.className === 'preview-volume');
  assert.ok(volume, 'preview must provide a volume control group');
  const event = { deltaY: 100, preventDefault() { this.prevented = true; } };
  volume.props.onWheel(event);
  assert.equal(event.prevented, true);
  assert.equal(transport.media.volume, 0.95);
  assert.equal(transport.media.muted, false);
  transport.flush();
  assert.equal(transport.audio().volume, 0.95);
});

test('muting and unmuting preserve the chosen media volume', () => {
  const transport = renderTransport();
  const mute = transport.find(node => node.type === 'button' && node.props['aria-label'] === '静音');
  assert.ok(mute, 'preview must provide a mute button');
  transport.media.volume = 0.35;
  mute.props.onClick();
  assert.equal(transport.media.muted, true);
  assert.equal(transport.media.volume, 0.35);
  mute.props.onClick();
  assert.equal(transport.media.muted, false);
  assert.equal(transport.media.volume, 0.35);
});

test('unmuting from zero restores the last audible level', () => {
  const transport = renderTransport();
  const slider = transport.find(node => node.type === 'input' && node.props['aria-label'] === '播放音量');
  const mute = transport.find(node => node.type === 'button' && node.props['aria-label'] === '静音');
  assert.ok(slider && mute, 'preview must provide volume controls');
  slider.props.onChange({ currentTarget: { value: '60' } });
  transport.media.dispatchEvent(new Event('volumechange'));
  slider.props.onChange({ currentTarget: { value: '0' } });
  transport.media.dispatchEvent(new Event('volumechange'));
  mute.props.onClick();
  assert.equal(transport.media.volume, 0.6);
  assert.equal(transport.media.muted, false);
});

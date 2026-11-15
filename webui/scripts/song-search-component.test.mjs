import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { runInNewContext } from 'node:vm';
import { updateSongTitle } from '../src/lib/editor.ts';

const { transformSync } = createRequire(import.meta.url)('next/dist/build/swc');
let cursor = 0;
const states = [];
const react = { useState: value => { const index = cursor++; if (!(index in states)) states[index] = value; return [states[index], next => { states[index] = next; }]; }, useRef: value => ({ current: value }), useEffect: () => {} };
const jsx = (type, props) => typeof type === 'function' ? type(props) : ({ type, props });
function load(name) {
  const component = { exports: {} };
  const source = readFileSync(new URL(`../src/components/${name}.tsx`, import.meta.url), 'utf8');
  const { code } = transformSync(source, { jsc: { parser: { syntax: 'typescript', tsx: true }, transform: { react: { runtime: 'automatic' } } }, module: { type: 'commonjs' } });
  runInNewContext(code, { exports: component.exports, module: component, require: dependency => {
    if (dependency === 'react') return react;
    if (dependency === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'fragment' };
    if (dependency === '@/lib/songSearch') return { searchSongs: async () => ({ songs: [], errors: [] }) };
    if (dependency === '@/lib/format') return { errorText: String, mediaTime: String };
    if (dependency === '@/lib/titleCandidates') return { titleCandidates: () => [] };
    if (dependency === '@/lib/editor') return { updateSongTitle };
    if (dependency === './Icon') return { Icon: () => null };
    if (dependency === './BoundaryNudge') return { BoundaryNudge: () => null };
    if (dependency === './SongSearch') return load('SongSearch');
    if (dependency === './SongLyrics') return load('SongLyrics');
    if (dependency === './SongSearchDialog') return load('SongSearchDialog');
    if (dependency === './Material') return { MaterialDialog: props => props.open ? { type: 'dialog', props } : null,
      Button: props => ({type:'button',props}), IconButton: props => ({type:'button',props}),
      TextField: props => ({type:'input',props}), Field: props => ({type:'input',props}) };
    throw new Error(`Unexpected import: ${dependency}`);
  } });
  return component.exports;
}

test('song catalog controls render only while editing an identified clip', () => {
  cursor = 0;
  states.length = 0;
  const props = load('SongProperties').SongProperties;
  const empty = props({ clip: undefined, duration: 0, onChange: () => {} });
  assert.equal(find(empty, node => node.props?.className === 'song-search'), null);
  const clip = { id: 'clip', start_seconds: 1, end_seconds: 10, title: '稻香', artist: '周杰伦', name: '稻香.mp4' };
  const changed = [];
  const editing = props({ clip, duration: 20, onChange: value => changed.push(value) });
  assert.equal(find(editing, node => node.props?.className === 'song-search'), null);
  assert.ok(find(editing, node => node.type === 'button' && node.props.children === '搜索歌曲'));
  const title = find(editing, node => node.props?.value === '稻香');
  title.props.onChange('夜曲');
  assert.equal(changed[0].title, '夜曲');
  assert.equal(changed[0].name, '夜曲.mp4');
});

test('search dialog opens from its launcher and dismisses through the dialog', () => {
  states.length = 0;
  const Dialog = load('SongSearchDialog').SongSearchDialog;
  const selected = [];
  const render = () => { cursor = 0; return Dialog({ initialQuery: '稻香', onChoose: song => selected.push(song) }); };
  const initial = render();
  assert.equal(find(initial, node => node.type === 'dialog'), null);
  find(initial, node => node.type === 'button').props.onClick();
  const opened = render();
  assert.ok(find(opened, node => node.type === 'dialog'));
  const search = find(opened, node => node.props?.['aria-label'] === '在线搜索歌曲');
  assert.ok(search);
  find(opened, node => node.type === 'dialog').props.onClose();
  assert.equal(find(render(), node => node.type === 'dialog'), null);
});

function find(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (predicate(node)) return node;
  return [node.props?.children].flat(Infinity).map(child => find(child, predicate)).find(Boolean) ?? null;
}

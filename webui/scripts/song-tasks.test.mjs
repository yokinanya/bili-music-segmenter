import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { runInNewContext } from 'node:vm';
import { matchesExport } from '../src/lib/exportSnapshot.ts';

const { transformSync } = createRequire(import.meta.url)('next/dist/build/swc');
function render(mode, job = null) {
  let slot = 0;
  const source = readFileSync(new URL('../src/components/SongTasks.tsx', import.meta.url), 'utf8');
  const { code } = transformSync(source, { jsc: { parser: { syntax: 'typescript', tsx: true }, transform: { react: { runtime: 'automatic' } } }, module: { type: 'commonjs' } });
  const module = { exports: {} };
  const jsx = (type, props) => typeof type === 'function' ? type(props) : ({ type, props });
  runInNewContext(code, { exports: module.exports, module, require: name => {
    if (name === 'react') return { useEffect: () => {}, useState: value => [slot++ === 1 ? job : value, () => {}] };
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'fragment' };
    if (name === './Material') return { MaterialDialog: props => props.open ? { type: 'dialog', props } : null,
      ActionLink: props => ({type:'a',props}), Button: props => ({ type: 'button', props }), Switch: props => ({ type: 'switch', props }), Progress: props => ({ type: 'progress', props }) };
    if (name === '@/lib/exportSnapshot') return { matchesExport };
    if (name === './Parameters') return { Parameters: () => null };
    if (name === './AnalysisProgress') return { AnalysisProgress: props => ({type:'progress',props}) };
    if (name === '@/lib/api') return { api: {} };
    if (name === '@/lib/editorApi') return { editorApi: {}, exportUrl: () => '' };
    if (name === '@/lib/format') return { errorText: String };
    throw new Error(name);
  } });
  return module.exports.SongTasks({ mode, project: { id: 'p', revision: 1, clips: [] }, selected: [], save: async () => {}, apply: () => {}, onClose: () => {} });
}
function text(node) {
  if (!node || typeof node === 'boolean') return '';
  if (typeof node !== 'object') return String(node);
  return [node.props?.children].flat(Infinity).map(text).join(' ');
}
test('AI dialog exposes analysis only and export dialog exposes exports only', () => {
  const ai = text(render('analysis'));
  assert.ok(ai.includes('开始分析'));
  assert.equal(ai.includes('导出选中区间'), false);
  const exporting = text(render('export'));
  assert.ok(exporting.includes('导出选中区间'));
  assert.equal(exporting.includes('开始分析'), false);
  assert.equal(text(render(null)), '');
});
test('running analysis has one stop action and an indeterminate progress indicator', () => {
  const tree = render('analysis', { id: 'j', state: 'running', batch: [], stop_requested: false });
  assert.equal(text(tree).includes('开始分析'), false);
  assert.ok(text(tree).includes('停止分析'));
  assert.ok(JSON.stringify(tree).includes('progress'));
});
test('failed analysis exposes nested recognizer errors rather than claiming completion', () => {
  const tree = render('analysis', { id: 'j', state: 'failed', error: null, batch: [{ error: '执行进程退出：1', steps: [{state:'failed', label:'shazam 识曲', error:'TimeoutError'}] }] });
  assert.ok(text(tree).includes('TimeoutError'));
  assert.ok(text(tree).includes('部分结果'));
});

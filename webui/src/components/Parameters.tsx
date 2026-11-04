import type { RunOptions } from '@/lib/types';
import { Field, Switch } from './Material';
import { Disclosure } from './Disclosure';
const FIELDS: { name: keyof RunOptions; label: string; step?: string; min?: string; max?: string }[] = [
  { name: 'minimum_confidence', label: '最低置信度', step: '.01', min: '.01', max: '1' },
  { name: 'minimum_singing_seconds', label: '最短演唱 / 秒', min: '1' },
  { name: 'scan_concurrency', label: '扫描并发', min: '1' },
  { name: 'candidate_concurrency', label: '候选并发', min: '1' },
];
const ADVANCED = [
  ['model_concurrency', '模型请求并发'], ['recognizer_concurrency', '识曲请求并发'],
  ['upload_concurrency', 'S3 上传并发'], ['media_concurrency', '媒体进程并发'],
  ['chunk_seconds', '扫描块时长 / 秒'], ['chunk_context_seconds', '扫描上下文 / 秒'],
  ['boundary_context_seconds', '边界上下文 / 秒'], ['minimum_candidate_seconds', '最短候选 / 秒'],
] as const;
export function Parameters({ options, onChange }: { options: RunOptions; onChange: (value: RunOptions) => void }) {
  const set = (name: keyof RunOptions, value: number | boolean) => onChange({ ...options, [name]: value });
  return <section className="parameters"><div className="section-head"><h2>任务参数</h2></div>
    <div className="field-grid">{FIELDS.map(({ name, ...props }) => <Field key={name} {...props} value={Number(options[name])} onChange={(value) => set(name, value)} />)}</div>
    <Switch label="Shazam 识曲" checked={options.use_shazam} onChange={(value) => set('use_shazam', value)} />
    <Switch label="网易云识曲" checked={options.use_netease} onChange={(value) => set('use_netease', value)} />
    <Switch label="模型判断标题冲突" checked={options.use_title_model} onChange={(value) => set('use_title_model', value)} />
    <Disclosure title="高级设置">
      <div className="field-grid">{ADVANCED.map(([name, label]) => <Field key={name} label={label} value={options[name]} min={name.includes('context') ? '0' : '1'} onChange={(value) => set(name, value)} />)}</div>
    </Disclosure>
  </section>;
}

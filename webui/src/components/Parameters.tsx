import type { RunOptions } from '@/lib/types';
import { Field, Switch } from './Material';
import { Disclosure } from './Disclosure';
export { validateParameters } from '@/lib/parameterValidation';
const FIELDS: { name: keyof RunOptions; label: string; step?: string; min?: string; max?: string }[] = [
  { name: 'minimum_confidence', label: '最低置信度', step: '.01', min: '.01', max: '1' },
  { name: 'minimum_singing_seconds', label: '最短演唱 / 秒', min: '1' },
];
const ADVANCED = [
  ['minimum_candidate_seconds', '最短候选 / 秒'], ['recognizer_timeout', '识曲超时 / 秒'],
] as const;
export function Parameters({ options, onChange }: { options: RunOptions; onChange: (value: RunOptions) => void }) {
  const set = (name: keyof RunOptions, value: number | boolean) => onChange({ ...options, [name]: value });
  return <section className="parameters"><div className="section-head"><h2>任务参数</h2></div>
    <div className="field-grid">{FIELDS.map(({ name, ...props }) => <Field key={name} {...props} value={Number(options[name])} onChange={(value) => set(name, value)} />)}</div>
    <Switch label="Shazam 识曲" checked={options.use_shazam} onChange={(value) => set('use_shazam', value)} />
    <Switch label="网易云识曲" checked={options.use_netease} onChange={(value) => set('use_netease', value)} />
    <Disclosure title="高级设置">
      <p className="helper">下面两项一般不用改。识曲超时是整首歌所有采样点的总时限。</p>
      <div className="field-grid">{ADVANCED.map(([name, label]) => <Field key={name} label={label} value={options[name]} min="1" onChange={(value) => set(name, value)} />)}</div>
    </Disclosure>
  </section>;
}
